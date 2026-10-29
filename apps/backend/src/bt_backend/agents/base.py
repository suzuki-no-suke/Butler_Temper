from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from bt_backend.agents.llm import LlmSession
from bt_backend.agents.types import AgentInfo, ChatTurn


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


@dataclass
class TurnResult:
    text: str
    parts: list[dict[str, Any]] | None = None
    state: dict[str, Any] = field(default_factory=dict)


class Agent[S: AgentSettings](ABC):
    id: str
    name: str
    description: str
    models: dict[str, str]
    settings_model: type[S]

    def info(self) -> AgentInfo:
        return AgentInfo(
            id=self.id,
            name=self.name,
            description=self.description,
            models=dict(self.models),
            default_settings=self.settings_model().model_dump(),
        )

    def parse_settings(self, raw: dict[str, Any]) -> S:
        return self.settings_model.model_validate(raw)

    @abstractmethod
    def run(self, settings: S, ctx: TurnContext) -> TurnResult: ...
