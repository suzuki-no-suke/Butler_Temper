from typing import Any

from bt_backend.agents import claude_simple
from bt_backend.agents.base import Agent
from bt_backend.agents.conversation import script_follower
from bt_backend.agents.conversation.base import ConversationCore
from bt_backend.agents.himitoku_gachi import HimitokuGachiAgent
from bt_backend.agents.secret_keeper import SecretKeeperAgent
from bt_backend.agents.secret_relay import SecretRelayAgent

_AGENTS: list[Agent[Any]] = [
    SecretKeeperAgent(),
    SecretRelayAgent(),
    HimitokuGachiAgent(),
    *claude_simple.AGENTS,
]
AGENTS: dict[str, Agent[Any]] = {a.id: a for a in _AGENTS}

# 会話用エージェントの AgentCore。既存の AgentCore とは別に持ち、混ぜて使わない
_CONVERSATION_AGENTS: list[ConversationCore[Any]] = [*script_follower.CORES]
CONVERSATION_AGENTS: dict[str, ConversationCore[Any]] = {a.id: a for a in _CONVERSATION_AGENTS}
