"""BOT の Agent。

Agent はコードで定義する。使うモデルと処理の流れは Agent ごとに固定で、
それ以外の設定は一つの JSON（Agent ごとの設定モデル）で書く。
LLM の呼び出しに関わるソースはすべてこのフォルダに置く。
このフォルダ全体が、通信時のソースのバックアップ対象になる。
呼び出す側は、このファイルが公開するものだけを使う。
"""

from bt_backend.agents.assist.settings_chat import ChatLine, SettingsProposal, propose_settings
from bt_backend.agents.conversation.templates import referenced_templates
from bt_backend.agents.runner import (
    InvalidSettings,
    UnknownAgent,
    get_agent_info,
    get_conversation_agent_info,
    list_agents,
    list_conversation_agents,
    run_conversation_turn,
    run_turn,
    validate_conversation_settings,
    validate_settings,
)
from bt_backend.agents.types import AgentInfo, ChatTurn, Interrupt, TurnOutcome

__all__ = [
    "AgentInfo",
    "ChatLine",
    "ChatTurn",
    "Interrupt",
    "InvalidSettings",
    "SettingsProposal",
    "TurnOutcome",
    "UnknownAgent",
    "get_agent_info",
    "get_conversation_agent_info",
    "list_agents",
    "list_conversation_agents",
    "propose_settings",
    "referenced_templates",
    "run_conversation_turn",
    "run_turn",
    "validate_conversation_settings",
    "validate_settings",
]
