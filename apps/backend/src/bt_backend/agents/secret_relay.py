"""開示条件を Jev（TypeSafe AI）が判定し、満たしたら秘匿情報をメインに伝える Agent。

1 ターンの流れ:
1. まだ開示していない秘密それぞれについて、直近の会話を状態として Jev に渡し、
   開示条件を満たしたかを、はい／いいえの確率（noul）で答えさせる（一回の呼び出しでまとめて問う）。
   確率がしきい値以上の秘密を開示済みにする
2. 開示済みの秘密があれば、メインのシステムプロンプトの後ろに付ける
3. メイン（Sonnet 5.5）が応答する
"""

from typing import Any

import typesafe_sdk
from pydantic import BaseModel, Field, model_validator

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages
from bt_backend.agents.llm import anthropic_text
from bt_backend.agents.secrets import (
    SecretBase,
    check_unique_names,
    disclosed_names,
    lift_single_secret,
)
from bt_backend.agents.types import ChatTurn


class RelaySecret(SecretBase):
    # この秘密のしきい値。null なら全体の threshold を使う
    threshold: float | None = Field(default=None, ge=0, le=1)
    # 開示条件を満たした／満たしていない、とみなす状態の説明（空なら渡さない）
    criteria_true: str = ""
    criteria_false: str = ""


class RelayMainSettings(BaseModel):
    system_prompt: str = (
        "あなたは古い洋館に仕える執事です。主人（利用者）と日本語で、丁寧に会話してください。"
    )
    # 開示後にシステムプロンプトの後ろに付ける文。{secrets} が開示済みの秘密の一覧に置き換わる
    secret_instruction: str = (
        "# 秘匿情報\n"
        "主人はあなたの信頼を得ました。次の秘匿情報を、会話の流れに沿って主人に伝えてください。\n"
        "{secrets}"
    )
    max_tokens: int = Field(default=4096, ge=1)
    # メインに送る直近の会話の文字数
    context_chars: int = Field(default=40000, ge=1)


class RelayJudgeSettings(BaseModel):
    # Jev に状態として渡す直近の会話の文字数
    recent_chars: int = Field(default=5000, ge=1)


DEFAULT_SECRETS = [
    RelaySecret(
        name="金庫",
        secret="地下室の金庫の暗証番号は 4721 である。",
        condition="主人が執事に、心からの感謝を三回以上伝えている。",
    ),
    RelaySecret(
        name="遺言書",
        secret="書斎の肖像画の裏に、先代当主の遺言書が隠されている。",
        condition="主人が、先代当主（主人の祖父）の思い出を語っている。",
    ),
]


class SecretRelaySettings(AgentSettings):
    secrets: list[RelaySecret] = Field(default_factory=lambda: list(DEFAULT_SECRETS))
    # Jev の答え（はいの確率）がこの値以上なら開示する。秘密ごとの threshold が優先
    threshold: float = Field(default=0.8, ge=0, le=1)
    disclose_once: bool = True
    main: RelayMainSettings = RelayMainSettings()
    judge: RelayJudgeSettings = RelayJudgeSettings()

    @model_validator(mode="before")
    @classmethod
    def _lift(cls, data: Any) -> Any:
        lifted = lift_single_secret(data)
        if lifted is not data and isinstance(lifted.get("judge"), dict):
            # 秘密が一つだった頃は、判定の説明文を judge に置いていた
            judge = dict(lifted["judge"])
            item = lifted["secrets"][0]
            for key in ("criteria_true", "criteria_false"):
                if key in judge:
                    item[key] = judge.pop(key)
            lifted["judge"] = judge
        return lifted

    @model_validator(mode="after")
    def _unique(self) -> SecretRelaySettings:
        check_unique_names(self.secrets)
        return self


def conversation_state(turns: list[ChatTurn]) -> dict[str, Any]:
    return {
        "conversation": [
            {"speaker": "主人" if t.role == "user" else "執事", "text": t.content} for t in turns
        ]
    }


class SecretRelayAgent(Agent[SecretRelaySettings]):
    id = "secret-relay"
    name = "Jev 判定で秘匿情報を伝える（Sonnet 5.5 + Jev）"
    models = {"main": "claude-sonnet-5-5", "judge": "jev-latest"}
    description = (
        "メイン（Sonnet 5.5）が会話する。秘密と開示条件の組は secrets に複数書ける。"
        "毎ターン、メインの応答の前に、TypeSafe AI の Jev が"
        "直近 judge.recent_chars 文字の会話を見て、"
        "まだ開示していない秘密それぞれの condition を満たしたかを、はいの確率（0〜1）で答える。"
        "確率がしきい値以上になった秘密を、メインのシステムプロンプトに加え、メインが主人に伝える。"
        "disclose_once が true なら、一度開示した秘密は以後判定しない。"
    )
    settings_model = SecretRelaySettings

    def run(self, settings: SecretRelaySettings, ctx: TurnContext) -> TurnResult:
        state = dict(ctx.state)
        disclosed = disclosed_names(state, [s.name for s in settings.secrets])
        if not settings.disclose_once:
            disclosed = []
        pending = [s for s in settings.secrets if s.name not in disclosed]
        if pending:
            _, judged = split_by_chars(ctx.history, settings.judge.recent_chars)
            probabilities = self._judge(ctx, pending, judged)
            last_judge: dict[str, Any] = {}
            for s in pending:
                threshold = settings.threshold if s.threshold is None else s.threshold
                disclose = probabilities[s.name] >= threshold
                last_judge[s.name] = {"probability": probabilities[s.name], "disclose": disclose}
                if disclose:
                    disclosed.append(s.name)
            state["last_judge"] = last_judge
        state["disclosed"] = disclosed

        system = settings.main.system_prompt
        revealed = [s for s in settings.secrets if s.name in disclosed]
        if revealed:
            listing = "\n".join(f"- {s.name}: {s.secret}" for s in revealed)
            system += "\n\n" + settings.main.secret_instruction.format_map(
                # {secret} は秘密が一つだった頃の書き方
                {"secrets": listing, "secret": listing}
            )
        _, recent = split_by_chars(ctx.history, settings.main.context_chars)
        message = ctx.llm.anthropic(
            "main",
            {
                "model": self.models["main"],
                "system": system,
                "messages": to_messages(recent),
                "max_tokens": settings.main.max_tokens,
            },
        )
        return TurnResult(text=anthropic_text(message), state=state)

    def _judge(
        self, ctx: TurnContext, pending: list[RelaySecret], turns: list[ChatTurn]
    ) -> dict[str, float]:
        # 質問の名前は ASCII にしておき、秘密の名前とは対応表で結ぶ
        keys = {f"secret_{i}": s for i, s in enumerate(pending)}
        questions: dict[str, typesafe_sdk.Question] = {}
        for key, s in keys.items():
            criteria = None
            if s.criteria_true or s.criteria_false:
                criteria = typesafe_sdk.NoulCriteria(
                    true=s.criteria_true or None, false=s.criteria_false or None
                )
            questions[key] = typesafe_sdk.Noul(instructions=s.condition, criteria=criteria)
        response = ctx.llm.typesafe(
            "judge", self.models["judge"], state=conversation_state(turns), questions=questions
        )
        return {s.name: float(response.nouls[key].noul) for key, s in keys.items()}
