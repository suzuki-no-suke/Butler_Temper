from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from bt_backend.agents.llm import LlmSession
from bt_backend.agents.types import (
    AgentInfo,
    ChatTurn,
    ContinuationAccess,
    Interrupt,
    SimulatorAccess,
)


class AgentPause(Exception):
    """Agent が会話を一時停止するときに投げる。メッセージをそのままエラーとして表示する。

    元の例外は __cause__ に入れる。
    """


class AgentSettings(BaseModel):
    """Agent の設定。項目の書き間違いに気づけるよう、知らない項目はエラーにする。"""

    model_config = ConfigDict(extra="forbid")


@dataclass
class TurnContext:
    # これまでの会話と、今回の利用者の発言（最後の要素）
    history: list[ChatTurn]
    # 前のターンまでの Agent の状態
    state: dict[str, Any]
    llm: LlmSession
    # まだ伝えていない割込み要求
    interrupts: list[Interrupt] = field(default_factory=list)
    # 使えるシミュレータ。呼ぶかどうかは Agent が決める
    simulators: SimulatorAccess = field(default_factory=SimulatorAccess)
    # 会話をまたぐ記録を読む口
    continuations: ContinuationAccess = field(default_factory=ContinuationAccess)


@dataclass
class TurnResult:
    text: str
    parts: list[dict[str, Any]] | None = None
    state: dict[str, Any] = field(default_factory=dict)
    # 会話をまたぐ記録に書くもの（キー -> 中身）
    continuations: dict[str, dict[str, Any]] = field(default_factory=dict)


class Agent[S: AgentSettings](ABC):
    id: str
    name: str
    description: str
    models: dict[str, str]
    settings_model: type[S]
    # 割込み要求を伝えられる相手。空なら割込みを受け付けない
    interrupt_targets: tuple[str, ...] = ()

    def info(self) -> AgentInfo:
        return AgentInfo(
            id=self.id,
            name=self.name,
            description=self.description,
            models=dict(self.models),
            default_settings=self.settings_model().model_dump(),
            interrupt_targets=list(self.interrupt_targets),
        )

    def parse_settings(self, raw: dict[str, Any]) -> S:
        return self.settings_model.model_validate(raw)

    @abstractmethod
    def run(self, settings: S, ctx: TurnContext) -> TurnResult: ...
