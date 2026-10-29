from typing import Any

from bt_backend.agents import claude_simple
from bt_backend.agents.base import Agent
from bt_backend.agents.secret_keeper import SecretKeeperAgent
from bt_backend.agents.secret_relay import SecretRelayAgent

_AGENTS: list[Agent[Any]] = [SecretKeeperAgent(), SecretRelayAgent(), *claude_simple.AGENTS]
AGENTS: dict[str, Agent[Any]] = {a.id: a for a in _AGENTS}
