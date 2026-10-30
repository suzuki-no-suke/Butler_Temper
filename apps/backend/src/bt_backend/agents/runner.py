from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from bt_backend.agents.base import AgentPause, TurnContext
from bt_backend.agents.conversation.base import SpeakContext
from bt_backend.agents.llm import LlmSession, is_not_found
from bt_backend.agents.registry import AGENTS, CONVERSATION_AGENTS
from bt_backend.agents.types import AgentInfo, ChatTurn, Interrupt, SimulatorAccess, TurnOutcome


class UnknownAgent(Exception):
    pass


class InvalidSettings(Exception):
    pass


def list_agents() -> list[AgentInfo]:
    return [a.info() for a in AGENTS.values()]


def get_agent_info(agent_id: str) -> AgentInfo:
    if agent_id not in AGENTS:
        raise UnknownAgent(agent_id)
    return AGENTS[agent_id].info()


def validate_settings(agent_id: str, settings: dict[str, Any]) -> None:
    if agent_id not in AGENTS:
        raise UnknownAgent(agent_id)
    try:
        AGENTS[agent_id].parse_settings(settings)
    except ValidationError as e:
        raise InvalidSettings(str(e)) from e


def run_turn(
    agent_id: str,
    settings: dict[str, Any],
    history: list[ChatTurn],
    state: dict[str, Any],
    api_keys: Mapping[str, str | None],
    interrupts: list[Interrupt] | None = None,
    simulators: SimulatorAccess | None = None,
) -> TurnOutcome:
    """1 ターン分を実行する。失敗しても例外は投げず TurnOutcome に入れる。"""
    outcome = TurnOutcome(state=state)
    agent = AGENTS.get(agent_id)
    if agent is None:
        outcome.error = f"AgentCore が見つかりません: {agent_id}"
        return outcome
    llm = LlmSession(api_keys)
    try:
        parsed = agent.parse_settings(settings)
        ctx = TurnContext(
            history=history,
            state=dict(state),
            llm=llm,
            interrupts=list(interrupts or []),
            simulators=simulators or SimulatorAccess(),
        )
        result = agent.run(parsed, ctx)
        outcome.text = result.text
        outcome.parts = result.parts
        outcome.state = result.state
    except AgentPause as e:
        outcome.error = str(e)
        cause = e.__cause__
        outcome.model_unavailable = isinstance(cause, Exception) and is_not_found(cause)
    except Exception as e:  # noqa: BLE001 - エラーは保存して止めるため、種類を問わず受け取る
        outcome.error = f"{type(e).__name__}: {e}"
        outcome.model_unavailable = is_not_found(e)
    outcome.exchanges = llm.exchanges
    return outcome


def list_conversation_agents() -> list[AgentInfo]:
    return [a.info() for a in CONVERSATION_AGENTS.values()]


def get_conversation_agent_info(agent_id: str) -> AgentInfo:
    if agent_id not in CONVERSATION_AGENTS:
        raise UnknownAgent(agent_id)
    return CONVERSATION_AGENTS[agent_id].info()


def validate_conversation_settings(agent_id: str, settings: dict[str, Any]) -> None:
    if agent_id not in CONVERSATION_AGENTS:
        raise UnknownAgent(agent_id)
    try:
        CONVERSATION_AGENTS[agent_id].parse_settings(settings)
    except ValidationError as e:
        raise InvalidSettings(str(e)) from e


def run_conversation_turn(
    agent_id: str,
    settings: dict[str, Any],
    history: list[ChatTurn],
    state: dict[str, Any],
    api_keys: Mapping[str, str | None],
    templates: Mapping[str, str],
    simulators: SimulatorAccess | None = None,
) -> TurnOutcome:
    """会話用エージェントの発言を一つ作る。失敗しても例外は投げず TurnOutcome に入れる。

    返すのは発言の文と状態だけで、表示用の内訳（parts）は持たない（人間の発言と同じ扱い）。
    """
    outcome = TurnOutcome(state=state)
    core = CONVERSATION_AGENTS.get(agent_id)
    if core is None:
        outcome.error = f"会話用エージェントの AgentCore が見つかりません: {agent_id}"
        return outcome
    llm = LlmSession(api_keys)
    try:
        parsed = core.parse_settings(settings)
        ctx = SpeakContext(
            history=history,
            state=dict(state),
            llm=llm,
            templates=dict(templates),
            simulators=simulators or SimulatorAccess(),
        )
        result = core.speak(parsed, ctx)
        if result.text == "":
            raise ValueError("会話用エージェントの発言が空でした")
        outcome.text = result.text
        outcome.state = result.state
    except Exception as e:  # noqa: BLE001 - エラーは保存して止めるため、種類を問わず受け取る
        outcome.error = f"{type(e).__name__}: {e}"
        outcome.model_unavailable = is_not_found(e)
    outcome.exchanges = llm.exchanges
    return outcome
