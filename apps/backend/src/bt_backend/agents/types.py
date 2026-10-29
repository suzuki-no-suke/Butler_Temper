from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class BotSpec:
    provider: str
    # 役割ごとのモデル ID。会話には "chat" を使う
    models: dict[str, Any]
    # BOT 設定のバージョンの中身（system_prompt / params など）
    settings: dict[str, Any]


@dataclass(frozen=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class ChatOutcome:
    model: str
    text: str | None = None
    error: str | None = None
    # モデルが存在しない（404）ため、以後この BOT を実行すべきでない
    model_unavailable: bool = False
    exchanges: list[dict[str, Any]] = field(default_factory=list)
