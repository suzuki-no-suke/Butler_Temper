"""台本（テンプレート）に沿って、相手の Agent との会話をできるだけ続ける会話用エージェント。"""

from pydantic import Field

from bt_backend.agents.base import AgentSettings
from bt_backend.agents.context import split_by_chars, to_messages
from bt_backend.agents.conversation.base import ConversationCore, SpeakContext, SpeakResult
from bt_backend.agents.conversation.templates import expand_templates
from bt_backend.agents.llm import anthropic_text
from bt_backend.agents.types import ChatTurn

DEFAULT_SYSTEM_PROMPT = """\
あなたは、チャットボット（以下「相手」）と会話する人間の利用者を演じます。
下の台本に沿って会話を進め、できるだけ長く会話を続けてください。

- あなたの出力は、そのまま相手への発言として送られます。人間が入力欄に打ち込む文だけを書いてください
- ト書き・心の声・括弧書きの注釈・台本への言及は書かないでください
- 相手が台本から外れても会話を打ち切らず、自然な流れで台本の筋に戻してください
- 台本の終わりまで来ても会話を終わらせず、台本の雰囲気に沿った話題で続けてください

# 台本
{{template:台本サンプル}}"""


class ScriptFollowerSettings(AgentSettings):
    # {{template:名前}} の形でテンプレートを埋め込める
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    # 会話の最初に、会話用エージェントへ渡す指示（LLM API は利用者の発言から始まる必要があるため）
    opening_message: str = "（相手との会話を始めてください。最初の発言だけを書いてください）"
    max_tokens: int = Field(default=1024, ge=1)
    # 会話コンテキストとして送る直近の会話の文字数。これより前の会話は送らない
    context_chars: int = Field(default=40000, ge=1)


class ScriptFollowerCore(ConversationCore[ScriptFollowerSettings]):
    settings_model = ScriptFollowerSettings

    def __init__(self, agent_id: str, label: str, model: str) -> None:
        self.id = agent_id
        self.name = f"台本に沿って会話を続ける（{label}）"
        self.models = {"main": model}
        self.description = (
            f"{label}（{model}）が利用者役になり、システムプロンプトに埋め込んだ台本に沿って、"
            "相手の Agent との会話をできるだけ続ける。"
            "直近 context_chars 文字分の会話を毎回送り、"
            "それより前の会話は送らない（要約もしない）。"
        )

    def speak(self, settings: ScriptFollowerSettings, ctx: SpeakContext) -> SpeakResult:
        opening = ChatTurn(seq=-1, role="user", content=settings.opening_message)
        _, recent = split_by_chars([opening, *ctx.history], settings.context_chars)
        message = ctx.llm.anthropic(
            "main",
            {
                "model": self.models["main"],
                "system": expand_templates(settings.system_prompt, ctx.templates),
                "messages": to_messages(recent),
                "max_tokens": settings.max_tokens,
            },
        )
        return SpeakResult(text=anthropic_text(message).strip(), state=ctx.state)


CORES = [
    ScriptFollowerCore("conversation-script-sonnet", "Sonnet 5.5", "claude-sonnet-5-5"),
    ScriptFollowerCore("conversation-script-opus", "Opus 5.5", "claude-opus-5-5"),
]
