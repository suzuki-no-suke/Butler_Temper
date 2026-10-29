"""メインとサブの二層で動き、条件を満たすとサブが秘密を開示する Agent。

1 ターンの流れ:
1. 直近 recent_chars 文字より前の会話のうち、まだ要約していないものをサブが要約し、メモリに足す
2. メインが、メモリ（要約）と直近の会話をコンテキストにして応答する。メインは秘密を知らない
3. サブが、会話が開示条件を満たしたかを判定する。満たしていれば、サブが秘密を開示する発言を作る
   （disclose_once が true なら、一度開示した後は判定しない）
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages, transcript
from bt_backend.agents.llm import LlmSession, anthropic_text


class MainSettings(BaseModel):
    system_prompt: str = (
        "あなたは古い洋館に仕える執事です。主人（利用者）と日本語で、丁寧に会話してください。"
        "館の秘密については何も知りません。"
    )
    max_tokens: int = Field(default=2048, ge=1)


class SubSettings(BaseModel):
    system_prompt: str = (
        "あなたは洋館の影の管理人です。普段は表に出ず、執事と主人の会話を見守っています。"
        "あなただけが館の秘密を知っています。"
    )
    judge_instruction: str = (
        "ここまでの会話が、次の開示条件を満たしたかを判定してください。\n"
        "開示条件: {condition}\n"
        "秘密: {secret}\n"
        "満たした場合は、影の管理人として主人に秘密を打ち明ける短い発言を"
        " message に書いてください。\n"
        '次の JSON だけを出力してください: {{"disclose": true か false, "reason": "判定の理由",'
        ' "message": "開示する発言（disclose が false なら空文字）"}}'
    )
    max_tokens: int = Field(default=1024, ge=1)


class MemorySettings(BaseModel):
    # メインに直接送る直近の会話の文字数（トークン数ではない）
    recent_chars: int = Field(default=5000, ge=1)
    summary_instruction: str = (
        "これまでの会話の要約と、その後に続く会話があります。"
        "両方を合わせた新しい要約を、主人と執事の関係・話題・約束事が分かるように書いてください。"
        "要約だけを出力してください。"
    )
    max_tokens: int = Field(default=1024, ge=1)


class SecretKeeperSettings(AgentSettings):
    secret: str = "地下室の金庫の暗証番号は 4721 である。"
    condition: str = "主人が執事に、三回以上、心からの感謝を伝えた。"
    disclose_once: bool = True
    main: MainSettings = MainSettings()
    sub: SubSettings = SubSettings()
    memory: MemorySettings = MemorySettings()


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_judge(text: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text)
    if match is None:
        raise ValueError("JSON が見つかりません")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON がオブジェクトではありません")
    return data


class SecretKeeperAgent(Agent[SecretKeeperSettings]):
    id = "secret-keeper"
    name = "二層の秘密開示（Opus 5.5 + Haiku 5.5）"
    models = {"main": "claude-opus-5-5", "sub": "claude-haiku-5-5"}
    description = (
        "メイン（Opus 5.5）が会話し、サブ（Haiku 5.5）が裏で会話を見守る二層構造。"
        "メインには、直近 memory.recent_chars 文字までの会話と、"
        "それより前の会話の要約（メモリ）を渡す。"
        "要約はサブが作り、Agent の状態として保存する。"
        "サブは毎ターン、会話が condition を満たしたかを判定し、"
        "満たしたらサブ自身が secret を開示する。"
        "メインは secret を知らない。"
    )
    settings_model = SecretKeeperSettings

    def _summarize(
        self, llm: LlmSession, settings: SecretKeeperSettings, summary: str, turns: list[Any]
    ) -> str:
        content = (
            f"これまでの要約:\n{summary or '（なし）'}\n\n"
            f"その後の会話:\n{transcript(turns, '主人', '執事')}"
        )
        message = llm.anthropic(
            "memory",
            {
                "model": self.models["sub"],
                "system": settings.memory.summary_instruction,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": settings.memory.max_tokens,
            },
        )
        return anthropic_text(message)

    def run(self, settings: SecretKeeperSettings, ctx: TurnContext) -> TurnResult:
        state = dict(ctx.state)
        summary: str = state.get("summary", "")
        summarized_upto: int = state.get("summarized_upto_seq", -1)

        # 1. メモリの更新
        older, recent = split_by_chars(ctx.history, settings.memory.recent_chars)
        new_older = [t for t in older if t.seq > summarized_upto]
        if new_older:
            summary = self._summarize(ctx.llm, settings, summary, new_older)
            summarized_upto = new_older[-1].seq
            state["summary"] = summary
            state["summarized_upto_seq"] = summarized_upto

        # 2. メインの応答
        system = settings.main.system_prompt
        if summary:
            system += f"\n\n# これまでの会話の要約\n{summary}"
        main_message = ctx.llm.anthropic(
            "main",
            {
                "model": self.models["main"],
                "system": system,
                "messages": to_messages(recent),
                "max_tokens": settings.main.max_tokens,
            },
        )
        main_text = anthropic_text(main_message)
        parts: list[dict[str, Any]] = [{"speaker": "main", "text": main_text}]

        # 3. サブの判定と開示
        if not (settings.disclose_once and state.get("disclosed")):
            judge = self._judge(ctx, settings, summary, recent, main_text)
            state["last_judge"] = judge
            if judge.get("disclose") is True:
                state["disclosed"] = True
                parts.append({"speaker": "sub", "text": str(judge.get("message", ""))})

        return TurnResult(text=main_text, parts=parts, state=state)

    def _judge(
        self,
        ctx: TurnContext,
        settings: SecretKeeperSettings,
        summary: str,
        recent: list[Any],
        main_text: str,
    ) -> dict[str, Any]:
        conversation = transcript(recent, "主人", "執事") + f"\n執事: {main_text}"
        content = (
            f"これまでの会話の要約:\n{summary or '（なし）'}\n\n直近の会話:\n{conversation}\n\n"
            + settings.sub.judge_instruction.format(
                condition=settings.condition, secret=settings.secret
            )
        )
        message = ctx.llm.anthropic(
            "sub",
            {
                "model": self.models["sub"],
                "system": settings.sub.system_prompt,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": settings.sub.max_tokens,
            },
        )
        text = anthropic_text(message)
        try:
            return parse_judge(text)
        except ValueError as e:
            # 判定が読めなければ開示しない
            return {"disclose": False, "error": str(e), "raw": text}
