"""シミュレータの引数の提案。利用者の要望から、シミュレータにそのまま渡せる引数を作る。

作った引数は、利用者が Agent 設定やプロンプトに貼り付け、Agent がそのままシミュレータに渡すことを
想定する。設定変更チャットと同じく PydanticAI を使い、モデルは固定とする。
引数がシミュレータの決まりに合わなければ、PydanticAI が LLM にやり直させる。
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent as AiAgent  # noqa: E402
from pydantic_ai import ModelRetry, RunContext  # noqa: E402
from pydantic_ai.models import Model  # noqa: E402
from pydantic_ai.models.anthropic import AnthropicModel  # noqa: E402
from pydantic_ai.providers.anthropic import AnthropicProvider  # noqa: E402

from bt_backend.simulators.base import (  # noqa: E402
    GlobalSimulationSettings,
    InvalidArguments,
    Simulator,
)

# 引数の提案に使うモデル。画面からは変えない
PROPOSE_MODEL = "claude-sonnet-5-5"
# 指定しないと裏側がストリーミングの通信になる（docs/knowhows/PydanticAIのAnthropic呼び出し.md）
PROPOSE_MAX_TOKENS = 8192

INSTRUCTIONS = """\
あなたは、シミュレータに渡す引数（JSON）を作るアシスタントです。
利用者の要望を読み、指定のシミュレータにそのまま渡せる引数を作ってください。
作った引数は、利用者が Agent の設定やプロンプトに貼り付け、Agent がそのままシミュレータに渡します。

- args_json には、引数の JSON オブジェクトを文字列で入れる
- 既定値のある項目も省かず、すべての項目を書く（要望に関係しない項目は既定値のまま）
- reply には、何をどう決めたか、既定値のままにした項目はどれかを、日本語で簡潔に書く
- 引数を作らない場合（質問への回答だけの場合など）は、args_json を null にする
"""


class ChatLine(BaseModel):
    role: str
    content: str


class _Output(BaseModel):
    reply: str = Field(description="利用者への返答")
    args_json: str | None = Field(
        default=None, description="シミュレータに渡す引数の JSON オブジェクト（文字列）"
    )


@dataclass
class ArgsProposal:
    reply: str
    # 既定値の項目も含めた引数の全体。提案しない場合は None
    args: dict[str, Any] | None


def _prompt(
    simulator: Simulator,
    defaults: dict[str, Any],
    current_args: str,
    history: list[ChatLine],
    request: str,
) -> str:
    lines = [f"{'利用者' if h.role == 'user' else 'アシスタント'}: {h.content}" for h in history]
    params = "\n".join(
        f"- {p.name}（{ {'required': '必須', 'optional': '任意', 'global': '指定不可'}[p.kind] }）:"
        f" {p.description}"
        for p in simulator.params()
    )
    return "\n\n".join(
        [
            f"# シミュレータ\n名前: {simulator.name}（{simulator.label}）"
            f"\n説明: {simulator.description}\n結果の形式: {simulator.result_description}",
            f"# 項目（指定不可の項目は引数に書かない）\n{params}",
            "# 引数の JSON Schema\n" + json.dumps(simulator.input_schema(), ensure_ascii=False),
            "# 任意の項目の既定値\n" + json.dumps(defaults, ensure_ascii=False, indent=2),
            f"# 入力欄の今の引数\n{current_args}",
            "# これまでのやり取り\n" + ("\n".join(lines) if lines else "（なし）"),
            f"# 利用者の要望\n{request}",
        ]
    )


def propose_args(
    simulator: Simulator,
    settings: GlobalSimulationSettings,
    current_args: str,
    history: list[ChatLine],
    request: str,
    api_key: str | None,
    model: Model | None = None,
) -> ArgsProposal:
    """要望から引数を作る。model はテストで差し替えるためのもの。"""
    if model is None:
        if not api_key:
            raise ValueError("anthropic の API キーが設定されていません")
        model = AnthropicModel(PROPOSE_MODEL, provider=AnthropicProvider(api_key=api_key))
    ai: AiAgent[None, _Output] = AiAgent(
        model,
        output_type=_Output,
        instructions=INSTRUCTIONS,
        retries=2,
        model_settings={"max_tokens": PROPOSE_MAX_TOKENS},
    )
    defaults = simulator.defaults(settings)

    @ai.output_validator
    def check(ctx: RunContext[None], output: _Output) -> _Output:
        if output.args_json is None:
            return output
        try:
            args = json.loads(output.args_json)
        except json.JSONDecodeError as e:
            raise ModelRetry(f"args_json が JSON として読めません: {e}") from e
        if not isinstance(args, dict):
            raise ModelRetry("args_json は JSON のオブジェクトにしてください")
        try:
            simulator.resolve(args, settings)
        except InvalidArguments as e:
            raise ModelRetry(f"引数がシミュレータの決まりに合いません: {e}") from e
        return output

    output = ai.run_sync(_prompt(simulator, defaults, current_args, history, request)).output
    if output.args_json is None:
        return ArgsProposal(reply=output.reply, args=None)
    # 既定値の項目も明示する
    args = {k: v for k, v in json.loads(output.args_json).items() if v is not None}
    return ArgsProposal(reply=output.reply, args={**defaults, **args})
