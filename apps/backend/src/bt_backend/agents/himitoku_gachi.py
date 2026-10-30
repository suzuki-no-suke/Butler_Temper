"""秘匿ガチ系261030。メイン・秘匿管理・記憶管理・システムの四役で動く Agent。

- メイン（Opus 5.5）: 利用者と会話する。直近 main.context_chars 文字の会話と記憶（要約）、
  開示済みの秘匿情報（思い出したこと）、システムからの通知をコンテキストにする
- 秘匿管理（Jev）: 毎ターン、まだ開示していない秘匿情報それぞれの開示条件を判定する。
  満たした秘匿情報は、メインの記憶として戻る
- 記憶管理（Haiku 5.5）: memory.every_turns 往復ごとに、
  前の要約とその後の会話（秘匿情報を含む）から、メインが覚えておくべき記憶を
  memory.max_chars 文字以内に要約し直す
- システム（LLM ではなくコード）: 毎ターン、規則（system.rules）と API から入った割込み要求を見て、
  通知をチャットウィンドウ・メイン・秘匿管理に選んで伝える。エラーが起きたら会話を一時停止する

1 ターンの流れ:
1. システムが、このターンの通知を決める
2. 秘匿管理（Jev）が判定する
3. メインが応答する
4. 往復数が memory.every_turns の倍数なら、記憶管理が要約を更新する
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from bt_backend.agents.base import Agent, AgentPause, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages, transcript
from bt_backend.agents.llm import anthropic_text
from bt_backend.agents.secret_relay import DEFAULT_SECRETS as RELAY_DEFAULT_SECRETS
from bt_backend.agents.secret_relay import RelaySecret, conversation_state, judge_with_jev
from bt_backend.agents.secrets import check_unique_names, disclosed_names
from bt_backend.agents.types import ChatTurn

# 通知を伝える相手
Target = Literal["window", "main", "secret"]
TARGETS: tuple[Target, ...] = ("window", "main", "secret")


class GachiMainSettings(BaseModel):
    system_prompt: str = (
        "あなたは古い洋館に仕える執事です。主人（利用者）と日本語で会話してください。"
    )
    length_instruction: str = (
        "# 応答の長さ\n"
        "自然な会話のように、場面に合わせて長さを変えてください。\n"
        "- 相槌や短い受け答え: 一言から数十文字\n"
        "- 普通の応答: 100 文字程度\n"
        "- 重要な応答: 重要さに応じて 400 文字、800 文字、1200 文字程度と、演説のように話す\n"
        "毎回同じ長さにしないでください。"
    )
    # 開示済みの秘匿情報を付ける文。{secrets} が開示済みの秘匿情報の一覧に置き換わる
    secret_instruction: str = (
        "# 思い出したこと\n"
        "会話の中で、次のことを思い出しました。あなた自身の記憶として、会話の流れに合わせて扱ってください。\n"
        "{secrets}"
    )
    # 記憶（要約）を付ける文。{summary} が要約に置き換わる
    memory_instruction: str = "# これまでの記憶\n{summary}"
    # システムからの通知を付ける文。{notices} が通知の一覧に置き換わる
    notice_instruction: str = (
        "# システムからの通知\n次の通知を踏まえて応答してください。\n{notices}"
    )
    max_tokens: int = Field(default=4096, ge=1)
    # メインに送る直近の会話の文字数（トークン数ではない）
    context_chars: int = Field(default=3000, ge=1)


class GachiSecretSettings(BaseModel):
    # Jev に状態として渡す直近の会話の文字数
    recent_chars: int = Field(default=3000, ge=1)


class GachiMemorySettings(BaseModel):
    # この往復数ごとに要約を更新する
    every_turns: int = Field(default=5, ge=1)
    # 要約の上限の文字数。指示文の {max_chars} に入る
    max_chars: int = Field(default=1000, ge=1)
    instruction: str = (
        "あなたは記憶の管理人です。これまでの記憶（要約）と、その後の執事と主人の会話、"
        "執事が思い出した秘匿情報があります。"
        "執事がこの先の会話のために覚えておくべきことを、"
        "{max_chars} 文字以内の新しい記憶にまとめてください。"
        "主人と執事の関係・話題・約束事・秘匿情報を落とさないでください。記憶だけを出力してください。"
    )
    max_tokens: int = Field(default=2048, ge=1)


class SystemRule(BaseModel):
    # 規則を見分ける名前（状態の記録に使う）
    name: str
    # every 往復ごとに通知する
    every: int | None = Field(default=None, ge=1)
    # over 往復を越えたら、毎ターン通知する
    over: int | None = Field(default=None, ge=0)
    targets: list[Target]
    # {turns} が往復数に置き換わる
    message: str

    @model_validator(mode="after")
    def _one_condition(self) -> SystemRule:
        if (self.every is None) == (self.over is None):
            raise ValueError("規則には every と over のどちらか一方だけを書いてください")
        return self

    def fires(self, turns: int) -> bool:
        if self.every is not None:
            return turns % self.every == 0
        assert self.over is not None
        return turns > self.over


class GachiSystemSettings(BaseModel):
    rules: list[SystemRule] = Field(
        default_factory=lambda: [
            SystemRule(
                name="10往復ごと",
                every=10,
                targets=["secret"],
                message="会話が {turns} 往復に達しました。",
            ),
            SystemRule(
                name="100往復超え",
                over=100,
                targets=["window", "main", "secret"],
                message=(
                    "会話が {turns} 往復となり、100 往復を越えました。"
                    "会話を締めくくり、終了に向かってください。"
                ),
            ),
        ]
    )
    # 一時停止のときにチャットウィンドウに出す文。{error} がエラーの内容に置き換わる
    pause_message: str = "システム: エラーが起きたため、会話を一時停止しました（{error}）"


class HimitokuGachiSettings(AgentSettings):
    secrets: list[RelaySecret] = Field(default_factory=lambda: list(RELAY_DEFAULT_SECRETS))
    # Jev の答え（はいの確率）がこの値以上なら開示する。秘匿情報ごとの threshold が優先
    threshold: float = Field(default=0.8, ge=0, le=1)
    disclose_once: bool = True
    main: GachiMainSettings = GachiMainSettings()
    secret: GachiSecretSettings = GachiSecretSettings()
    memory: GachiMemorySettings = GachiMemorySettings()
    system: GachiSystemSettings = GachiSystemSettings()

    @model_validator(mode="after")
    def _unique(self) -> HimitokuGachiSettings:
        check_unique_names(self.secrets)
        return self


class HimitokuGachiAgent(Agent[HimitokuGachiSettings]):
    id = "himitoku-gachi-261030"
    name = "秘匿ガチ系261030（Opus 5.5 + Jev + Haiku 5.5）"
    models = {"main": "claude-opus-5-5", "secret": "jev-latest", "memory": "claude-haiku-5-5"}
    description = (
        "メイン（Opus 5.5）・秘匿管理（Jev）・記憶管理（Haiku 5.5）・システム（コード）の四役。"
        "メインは直近 main.context_chars 文字の会話と記憶を持ち、場面に合わせた長さで話す。"
        "秘匿管理は毎ターン、まだ開示していない秘匿情報それぞれの開示条件を判定し、"
        "満たした秘匿情報をメインの記憶（思い出したこと）として戻す。"
        "記憶管理は memory.every_turns 往復ごとに、会話（秘匿情報を含む）を"
        "memory.max_chars 文字以内に要約し直す。"
        "システムは毎ターン、system.rules と API からの割込み要求を見て、"
        "通知をチャットウィンドウ（window）・メイン（main）・秘匿管理（secret）に選んで伝え、"
        "エラーが起きたら会話を一時停止する。"
    )
    settings_model = HimitokuGachiSettings
    interrupt_targets = TARGETS

    def run(self, settings: HimitokuGachiSettings, ctx: TurnContext) -> TurnResult:
        try:
            return self._run(settings, ctx)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise AgentPause(settings.system.pause_message.format(error=error)) from e

    def _run(self, settings: HimitokuGachiSettings, ctx: TurnContext) -> TurnResult:
        state = dict(ctx.state)
        turns = sum(1 for t in ctx.history if t.role == "user")

        # 1. システム
        notices = self._notices(settings, ctx, turns)
        state["system"] = {
            "turns": turns,
            "notices": notices,
            "delivered_interrupts": [i.id for i in ctx.interrupts],
        }

        def notices_for(target: Target) -> list[str]:
            return [n["message"] for n in notices if target in n["targets"]]

        memory: dict[str, Any] = dict(state.get("memory") or {})
        summary: str = memory.get("summary", "")

        # 2. 秘匿管理
        disclosed = disclosed_names(state, [s.name for s in settings.secrets])
        if not settings.disclose_once:
            disclosed = []
        pending = [s for s in settings.secrets if s.name not in disclosed]
        if pending:
            _, judged = split_by_chars(ctx.history, settings.secret.recent_chars)
            judge_state = conversation_state(judged)
            if summary:
                judge_state["memory"] = summary
            if secret_notices := notices_for("secret"):
                judge_state["system_notices"] = secret_notices
            probabilities = judge_with_jev(
                ctx, self.models["secret"], "secret", pending, judge_state
            )
            last_judge: dict[str, Any] = {}
            for s in pending:
                threshold = settings.threshold if s.threshold is None else s.threshold
                disclose = probabilities[s.name] >= threshold
                last_judge[s.name] = {"probability": probabilities[s.name], "disclose": disclose}
                if disclose:
                    disclosed.append(s.name)
            state["last_judge"] = last_judge
        state["disclosed"] = disclosed
        revealed = [s for s in settings.secrets if s.name in disclosed]

        # 3. メイン
        main = settings.main
        system = main.system_prompt + "\n\n" + main.length_instruction
        if summary:
            system += "\n\n" + main.memory_instruction.format_map({"summary": summary})
        if revealed:
            listing = "\n".join(f"- {s.secret}" for s in revealed)
            system += "\n\n" + main.secret_instruction.format_map({"secrets": listing})
        if main_notices := notices_for("main"):
            listing = "\n".join(f"- {n}" for n in main_notices)
            system += "\n\n" + main.notice_instruction.format_map({"notices": listing})
        _, recent = split_by_chars(ctx.history, main.context_chars)
        message = ctx.llm.anthropic(
            "main",
            {
                "model": self.models["main"],
                "system": system,
                "messages": to_messages(recent),
                "max_tokens": main.max_tokens,
            },
        )
        main_text = anthropic_text(message)

        # 4. 記憶管理
        if turns % settings.memory.every_turns == 0:
            upto: int = memory.get("summarized_upto_seq", -1)
            reply = ChatTurn(seq=ctx.history[-1].seq + 1, role="assistant", content=main_text)
            new_turns = [t for t in [*ctx.history, reply] if t.seq > upto]
            summary = self._summarize(ctx, settings, summary, new_turns, revealed)
            memory = {
                "summary": summary,
                "summarized_upto_seq": reply.seq,
                "updated_at_turn": turns,
            }
        state["memory"] = memory

        parts: list[dict[str, Any]] = [
            {"speaker": "system", "text": text} for text in notices_for("window")
        ]
        parts.append({"speaker": "main", "text": main_text})
        return TurnResult(text=main_text, parts=parts, state=state)

    def _notices(
        self, settings: HimitokuGachiSettings, ctx: TurnContext, turns: int
    ) -> list[dict[str, Any]]:
        notices: list[dict[str, Any]] = [
            {
                "source": f"rule:{rule.name}",
                "targets": list(rule.targets),
                "message": rule.message.format_map({"turns": turns}),
            }
            for rule in settings.system.rules
            if rule.fires(turns)
        ]
        notices += [
            {"source": f"interrupt:{i.id}", "targets": list(i.targets), "message": i.message}
            for i in ctx.interrupts
        ]
        return notices

    def _summarize(
        self,
        ctx: TurnContext,
        settings: HimitokuGachiSettings,
        summary: str,
        turns: list[ChatTurn],
        revealed: list[RelaySecret],
    ) -> str:
        secrets = "\n".join(f"- {s.secret}" for s in revealed) or "（なし）"
        content = (
            f"これまでの記憶:\n{summary or '（なし）'}\n\n"
            f"その後の会話:\n{transcript(turns, '主人', '執事')}\n\n"
            f"執事が思い出した秘匿情報:\n{secrets}"
        )
        message = ctx.llm.anthropic(
            "memory",
            {
                "model": self.models["memory"],
                "system": settings.memory.instruction.format_map(
                    {"max_chars": settings.memory.max_chars}
                ),
                "messages": [{"role": "user", "content": content}],
                "max_tokens": settings.memory.max_tokens,
            },
        )
        return anthropic_text(message)
