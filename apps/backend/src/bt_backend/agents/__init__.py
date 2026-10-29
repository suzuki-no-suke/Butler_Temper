"""BOT との会話で LLM を呼ぶモジュール。

LLM の呼び出しに関わるソースはすべてこのフォルダに置く。
このフォルダ全体が、通信時のソースのバックアップ対象になる。
呼び出す側は run_chat と、types の型だけを使う。
"""

from bt_backend.agents.chat import PROVIDERS, run_chat
from bt_backend.agents.types import BotSpec, ChatOutcome, ChatTurn

__all__ = ["PROVIDERS", "BotSpec", "ChatOutcome", "ChatTurn", "run_chat"]
