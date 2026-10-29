from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ChatTurn:
    seq: int
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AgentInfo:
    id: str
    name: str
    description: str
    # 役割 -> モデル ID（Agent ごとに固定）
    models: dict[str, str]
    default_settings: dict[str, Any]


@dataclass
class TurnOutcome:
    # 会話履歴に残す BOT の発言（次のターン以降、Agent に渡される）
    text: str | None = None
    # 表示用の内訳（例: メインとサブの発言）。無ければ text だけを表示する
    parts: list[dict[str, Any]] | None = None
    # このターンの後の Agent の状態（メモリなど）
    state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # モデルが存在しない（404）ため、以後この BOT を実行すべきでない
    model_unavailable: bool = False
    # HTTP でやり取りした内容。各要素の "label" は Agent 内での呼び出しの役割
    exchanges: list[dict[str, Any]] = field(default_factory=list)
