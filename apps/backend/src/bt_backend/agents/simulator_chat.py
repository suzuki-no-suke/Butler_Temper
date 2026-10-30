"""シミュレータを使って会話する Claude の Agent。

シミュレータを Messages API のツールとして見せる。使うかどうか・いつ使うかは LLM が決め、
その条件はシステムプロンプトに書く。AgentCore は応答の tool_use を検出してシミュレータを呼び、
結果を tool_result として返して続きの応答を得る。

表示用の内訳には、メインの発言と、シミュレータの呼び出しと結果だけを出す。
シミュレーションの中身（LLM シミュレータの各回の出力など）は、シミュレータの実行記録に残る。
"""

import json
from typing import Any

from pydantic import Field

from bt_backend.agents.base import Agent, AgentSettings, TurnContext, TurnResult
from bt_backend.agents.context import split_by_chars, to_messages
from bt_backend.agents.llm import anthropic_text

DEFAULT_SYSTEM_PROMPT = """\
あなたは丁寧な執事です。主人（利用者）と日本語で会話してください。

# シミュレータ
会話の途中で、ときどき唐突に「引いていかない？」と、おみくじやサイコロを主人に勧めてください。
主人がはっきり断らなければ、ツールでシミュレートし、結果を会話に織り込んで伝えてください。
結果を自分で決めてはいけません。必ずツールの結果を使ってください。
- omikuji: おみくじを引く
- dice: サイコロを 1 個振る（m は出目の最大）
- dice_sum: サイコロを n 個振って出目を合計する（m は出目の最大）
- llm: 答えの決まらない出来事（天気、勝負の行方など）を、条件をプロンプトに書いてシミュレートする"""


class SimulatorChatSettings(AgentSettings):
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_tokens: int = Field(default=4096, ge=1)
    # 会話コンテキストとして送る直近の会話の文字数。これより前の会話は送らない
    context_chars: int = Field(default=40000, ge=1)
    # ツールとして見せるシミュレータの名前
    simulators: list[str] = Field(default_factory=lambda: ["omikuji", "dice", "dice_sum", "llm"])
    # 1 ターンの中で、シミュレータを呼んで続きを得る往復の上限。超えたらツールを使わせずに応答させる
    max_tool_rounds: int = Field(default=4, ge=1)


def _block(block: Any) -> dict[str, Any]:
    # 思考のブロックも含め、受け取った内容をそのまま返す（ツールのやり取りの途中で落とさない）
    dumped: dict[str, Any] = block.model_dump(mode="json", exclude_none=True)
    return dumped


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class SimulatorChatAgent(Agent[SimulatorChatSettings]):
    settings_model = SimulatorChatSettings

    def __init__(self, agent_id: str, label: str, model: str) -> None:
        self.id = agent_id
        self.name = f"シミュレータを使う会話（{label}）"
        self.models = {"main": model}
        self.description = (
            f"{label}（{model}）が、システムプロンプトに書いた条件で、自分でシミュレータを呼ぶ。"
            "simulators に挙げたシミュレータをツールとして見せ、"
            "呼び出しと結果を表示用の内訳に出す。"
            "直近 context_chars 文字分の会話を毎回送る（ツールのやり取りは次のターンに送らない）。"
        )

    def run(self, settings: SimulatorChatSettings, ctx: TurnContext) -> TurnResult:
        _, recent = split_by_chars(ctx.history, settings.context_chars)
        messages: list[dict[str, Any]] = list(to_messages(recent))
        tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in ctx.simulators.tools
            if t.name in settings.simulators
        ]
        texts: list[str] = []
        parts: list[dict[str, Any]] = []
        simulated = False
        for round_ in range(settings.max_tool_rounds + 1):
            request: dict[str, Any] = {
                "model": self.models["main"],
                "system": settings.system_prompt,
                "messages": messages,
                "max_tokens": settings.max_tokens,
            }
            if tools:
                request["tools"] = tools
                if round_ == settings.max_tool_rounds:
                    request["tool_choice"] = {"type": "none"}
            message = ctx.llm.anthropic("main", request)
            text = anthropic_text(message)
            if text:
                texts.append(text)
                parts.append({"speaker": "main", "text": text})
            uses = [b for b in message.content if b.type == "tool_use"]
            if message.stop_reason != "tool_use" or not uses:
                break
            messages.append({"role": "assistant", "content": [_block(b) for b in message.content]})
            results: list[dict[str, Any]] = []
            for use in uses:
                args = dict(use.input) if isinstance(use.input, dict) else {}
                call = ctx.simulators.call(use.name, args)
                simulated = True
                parts.append(
                    {
                        "speaker": "simulation",
                        "text": f"呼び出し: {use.name} {_json(args)}\n結果: {_json(call.result)}",
                        "simulation_run_id": call.run_id,
                    }
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": _json(call.result),
                        "is_error": not call.ok,
                    }
                )
            messages.append({"role": "user", "content": results})
        return TurnResult(
            text="\n\n".join(texts), parts=parts if simulated else None, state=ctx.state
        )


AGENTS = [SimulatorChatAgent("simulator-chat-sonnet", "Sonnet 5.5", "claude-sonnet-5-5")]
