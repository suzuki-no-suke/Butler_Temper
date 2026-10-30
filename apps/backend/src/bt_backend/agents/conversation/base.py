from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from bt_backend.agents.base import AgentSettings
from bt_backend.agents.llm import LlmSession
from bt_backend.agents.types import AgentInfo, ChatTurn


@dataclass
class SpeakContext:
    # 会話用エージェントから見た会話。相手の Agent の発言が user、自分の発言が assistant
    history: list[ChatTurn]
    # 前のターンまでの会話用エージェントの状態
    state: dict[str, Any]
    llm: LlmSession
    # 埋め込めるテンプレート（名前 -> 本文）。会話の開始時のバージョンに固定されている
    templates: Mapping[str, str] = field(default_factory=dict)


@dataclass
class SpeakResult:
    # 相手の Agent に送る発言。人間の発言と同じく、文だけを出す
    text: str
    state: dict[str, Any] = field(default_factory=dict)


class ConversationCore[S: AgentSettings](ABC):
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
    def speak(self, settings: S, ctx: SpeakContext) -> SpeakResult: ...
