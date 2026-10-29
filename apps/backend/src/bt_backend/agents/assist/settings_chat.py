"""設定変更チャット。利用者の要望から、BOT の Agent 設定の変更案を作る。

PydanticAI を使い、Agent の設定モデルをそのまま出力の型にする。
型に合わない案は PydanticAI が LLM にやり直させるので、返る案は必ずその Agent の設定として正しい。
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, create_model

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent as AiAgent  # noqa: E402
from pydantic_ai.models import Model  # noqa: E402
from pydantic_ai.models.anthropic import AnthropicModel  # noqa: E402
from pydantic_ai.providers.anthropic import AnthropicProvider  # noqa: E402

from bt_backend.agents.registry import AGENTS  # noqa: E402

# 設定変更チャットに使うモデル。設定画面からは変えない
SETTINGS_CHAT_MODEL = "claude-sonnet-5-5"
# 指定しないと PydanticAI はモデルの上限を送り、Anthropic SDK の決まりで裏側がストリーミングの
# 通信になる。設定の変更案には足りる量を明示し、通常の（ストリーミングしない）通信にする
SETTINGS_CHAT_MAX_TOKENS = 8192

INSTRUCTIONS = """\
あなたは、対話相手となる Agent（チャットボット）の設定を調整する手伝いをするアシスタントです。
利用者は、Agent の振る舞いや性格がプロンプトや設定でどう変わるかを調べています。
Agent は、AgentCore（モデルの選択と処理の流れ）と、それに適用する Agent 設定（JSON）でできています。
利用者の要望を読み、編集中の Agent 設定をもとに変更案を作ってください。

- reply には、何をどう変えたか（変えなかった場合はその理由や、確認したいこと）を日本語で簡潔に書く
- 設定を変える場合は、settings に変更後の設定の全体を入れる。
  変えない項目も、編集中の値のまま必ず含める
- 設定を変えない場合（質問への回答だけの場合など）は、settings を null にする
- 要望に関係しない項目は変えない
"""


class ChatLine(BaseModel):
    role: str
    content: str


@dataclass
class SettingsProposal:
    reply: str
    # 変更後の設定の全体。変更しない場合は None
    settings: dict[str, Any] | None


def _output_type(agent_id: str) -> type[BaseModel]:
    # 出力の型を Agent ごとに組み立てるため、型検査では Any として扱う
    optional_settings: Any = AGENTS[agent_id].settings_model | None
    output: type[BaseModel] = create_model(
        "SettingsProposal",
        reply=(str, Field(description="利用者への返答")),
        settings=(
            optional_settings,
            Field(default=None, description="変更後の設定の全体。変えない場合は null"),
        ),
    )
    return output


def _prompt(agent_id: str, current_settings: str, history: list[ChatLine], request: str) -> str:
    info = AGENTS[agent_id].info()
    lines = [f"{'利用者' if h.role == 'user' else 'アシスタント'}: {h.content}" for h in history]
    models = json.dumps(info.models, ensure_ascii=False)
    defaults = json.dumps(info.default_settings, ensure_ascii=False, indent=2)
    return "\n\n".join(
        [
            f"# AgentCore\n名前: {info.name}\nモデル: {models}\n説明: {info.description}",
            f"# 既定の Agent 設定\n{defaults}",
            f"# 編集中の Agent 設定\n{current_settings}",
            "# これまでのやり取り\n" + ("\n".join(lines) if lines else "（なし）"),
            f"# 利用者の要望\n{request}",
        ]
    )


def propose_settings(
    agent_id: str,
    current_settings: str,
    history: list[ChatLine],
    request: str,
    api_key: str | None,
    model: Model | None = None,
) -> SettingsProposal:
    """要望から設定の変更案を作る。model はテストで差し替えるためのもの。"""
    if model is None:
        if not api_key:
            raise ValueError("anthropic の API キーが設定されていません")
        model = AnthropicModel(SETTINGS_CHAT_MODEL, provider=AnthropicProvider(api_key=api_key))
    ai = AiAgent(
        model,
        output_type=_output_type(agent_id),
        instructions=INSTRUCTIONS,
        retries=2,
        model_settings={"max_tokens": SETTINGS_CHAT_MAX_TOKENS},
    )
    output: Any = ai.run_sync(_prompt(agent_id, current_settings, history, request)).output
    settings = output.settings
    return SettingsProposal(
        reply=output.reply,
        settings=None if settings is None else settings.model_dump(mode="json"),
    )
