"""システムプロンプトだけを設定して会話する Claude の Agent。"""

from pydantic import Field

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages
from bt_backend.agents.llm import anthropic_text


class SimpleSettings(AgentSettings):
    system_prompt: str = "あなたは丁寧な執事です。主人（利用者）と日本語で会話してください。"
    max_tokens: int = Field(default=4096, ge=1)
    # 会話コンテキストとして送る直近の会話の文字数。これより前の会話は送らない
    context_chars: int = Field(default=40000, ge=1)


class SimpleClaudeAgent(Agent[SimpleSettings]):
    settings_model = SimpleSettings

    def __init__(self, agent_id: str, label: str, model: str) -> None:
        self.id = agent_id
        self.name = f"シンプル会話（{label}）"
        self.models = {"main": model}
        self.description = (
            f"{label}（{model}）とシステムプロンプトだけで会話する。"
            "直近 context_chars 文字分の会話を毎回送り、"
            "それより前の会話は送らない（要約もしない）。"
        )

    def run(self, settings: SimpleSettings, ctx: TurnContext) -> TurnResult:
        _, recent = split_by_chars(ctx.history, settings.context_chars)
        message = ctx.llm.anthropic(
            "main",
            {
                "model": self.models["main"],
                "system": settings.system_prompt,
                "messages": to_messages(recent),
                "max_tokens": settings.max_tokens,
            },
        )
        return TurnResult(text=anthropic_text(message), state=ctx.state)


AGENTS = [
    SimpleClaudeAgent("claude-simple-fable", "Fable 5.1", "claude-fable-5-1"),
    SimpleClaudeAgent("claude-simple-opus", "Opus 5.5", "claude-opus-5-5"),
    SimpleClaudeAgent("claude-simple-sonnet", "Sonnet 5.5", "claude-sonnet-5-5"),
    SimpleClaudeAgent("claude-simple-haiku", "Haiku 5.5", "claude-haiku-5-5"),
]
