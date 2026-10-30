from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ChatTurn:
    seq: int
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Interrupt:
    """API から入った割込み要求。次のターンに、targets に挙げた相手へ伝える。"""

    id: int
    message: str
    targets: list[str]


@dataclass(frozen=True)
class AgentInfo:
    id: str
    name: str
    description: str
    # 役割 -> モデル ID（Agent ごとに固定）
    models: dict[str, str]
    default_settings: dict[str, Any]
    # 割込み要求を伝えられる相手。空なら割込みを受け付けない
    interrupt_targets: list[str] = field(default_factory=list)


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


@dataclass(frozen=True)
class SimulatorTool:
    """Agent の LLM にツールとして見せるシミュレータ。中身は Agents の外にある。"""

    name: str
    # シミュレータが持つ短い固定の説明。いつ使うかは Agent の設定（プロンプト）に書く
    description: str
    # 引数の JSON Schema
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class SimulationCall:
    """シミュレータを 1 回呼んだ結果。"""

    # 実行記録の id。記録しなかった（シミュレータが無いなど）場合は None
    run_id: int | None
    ok: bool
    # LLM にツールの結果として返す内容。引数が足りないときは、その旨を判断できる形で返る
    result: dict[str, Any]


def _no_simulator(name: str, args: dict[str, Any]) -> SimulationCall:
    return SimulationCall(
        run_id=None, ok=False, result={"ok": False, "error": "シミュレータを使えません"}
    )


@dataclass
class SimulatorAccess:
    """1 ターンの間に Agent が使えるシミュレータ。呼ぶと実行記録が残る。"""

    tools: list[SimulatorTool] = field(default_factory=list)
    call: Callable[[str, dict[str, Any]], SimulationCall] = _no_simulator
