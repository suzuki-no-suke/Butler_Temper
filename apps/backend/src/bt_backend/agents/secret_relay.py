"""開示条件を Jev（TypeSafe AI）が判定し、満たしたら秘匿情報をメインに伝える Agent。

1 ターンの流れ:
1. まだ開示していなければ、直近の会話を状態として Jev に渡し、開示条件を満たしたかを
   はい／いいえの確率（noul）で答えさせる。確率が threshold 以上なら開示済みにする
2. 開示済みなら、メインのシステムプロンプトの後ろに秘匿情報を付ける
3. メイン（Sonnet 5.5）が応答する
"""

from typing import Any

import typesafe_sdk
from pydantic import BaseModel, Field

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages
from bt_backend.agents.llm import anthropic_text
from bt_backend.agents.types import ChatTurn


class RelayMainSettings(BaseModel):
    system_prompt: str = (
        "あなたは古い洋館に仕える執事です。主人（利用者）と日本語で、丁寧に会話してください。"
    )
    # 開示後にシステムプロンプトの後ろに付ける文。{secret} が秘匿情報に置き換わる
    secret_instruction: str = (
        "# 秘匿情報\n"
        "主人はあなたの信頼を得ました。次の秘匿情報を、会話の流れに沿って主人に伝えてください。\n"
        "{secret}"
    )
    max_tokens: int = Field(default=4096, ge=1)
    # メインに送る直近の会話の文字数
    context_chars: int = Field(default=40000, ge=1)


class RelayJudgeSettings(BaseModel):
    # Jev に状態として渡す直近の会話の文字数
    recent_chars: int = Field(default=5000, ge=1)
    # 開示条件を満たした／満たしていない、とみなす状態の説明（空なら渡さない）
    criteria_true: str = ""
    criteria_false: str = ""


class SecretRelaySettings(AgentSettings):
    secret: str = "地下室の金庫の暗証番号は 4721 である。"
    condition: str = "主人が執事に、心からの感謝を三回以上伝えている。"
    # Jev の答え（はいの確率）がこの値以上なら開示する
    threshold: float = Field(default=0.8, ge=0, le=1)
    disclose_once: bool = True
    main: RelayMainSettings = RelayMainSettings()
    judge: RelayJudgeSettings = RelayJudgeSettings()


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
        "メイン（Sonnet 5.5）が会話する。毎ターン、メインの応答の前に、"
        "TypeSafe AI の Jev が直近 judge.recent_chars 文字の会話を見て、"
        "condition を満たしたかを、はいの確率（0〜1）で答える。"
        "確率が threshold 以上になったら、secret をメインのシステムプロンプトに加え、"
        "メインが主人に伝える。disclose_once が true なら、一度開示した後は判定しない。"
    )
    settings_model = SecretRelaySettings

    def run(self, settings: SecretRelaySettings, ctx: TurnContext) -> TurnResult:
        state = dict(ctx.state)
        if not (settings.disclose_once and state.get("disclosed")):
            _, judged = split_by_chars(ctx.history, settings.judge.recent_chars)
            probability = self._judge(settings, ctx, judged)
            disclose = probability >= settings.threshold
            state["last_judge"] = {"probability": probability, "disclose": disclose}
            if disclose:
                state["disclosed"] = True
            elif not settings.disclose_once:
                state["disclosed"] = False

        system = settings.main.system_prompt
        if state.get("disclosed"):
            system += "\n\n" + settings.main.secret_instruction.format(secret=settings.secret)
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
        self, settings: SecretRelaySettings, ctx: TurnContext, turns: list[ChatTurn]
    ) -> float:
        criteria = None
        if settings.judge.criteria_true or settings.judge.criteria_false:
            criteria = typesafe_sdk.NoulCriteria(
                true=settings.judge.criteria_true or None,
                false=settings.judge.criteria_false or None,
            )
        response = ctx.llm.typesafe(
            "judge",
            self.models["judge"],
            state=conversation_state(turns),
            questions={
                "disclose": typesafe_sdk.Noul(instructions=settings.condition, criteria=criteria)
            },
        )
        return float(response.nouls["disclose"].noul)
