from collections.abc import Callable, Mapping, Sequence

import httpx2

from bt_backend.agents.capture import capturing_client
from bt_backend.agents.providers import anthropic_chat, gemini_chat, openai_chat
from bt_backend.agents.types import BotSpec, ChatOutcome, ChatTurn

ProviderFn = Callable[[BotSpec, Sequence[ChatTurn], str, httpx2.Client], str]

PROVIDERS: dict[str, ProviderFn] = {
    "anthropic": anthropic_chat.chat,
    "openai": openai_chat.chat_openai,
    "openrouter": openai_chat.chat_openrouter,
    "gemini": gemini_chat.chat,
}

# 各プロバイダーの「モデルが存在しない」を表す例外か判定する
_NOT_FOUND_CHECKS: list[Callable[[Exception], bool]] = [
    anthropic_chat.is_not_found,
    openai_chat.is_not_found,
    gemini_chat.is_not_found,
]


def run_chat(
    spec: BotSpec, history: Sequence[ChatTurn], api_keys: Mapping[str, str | None]
) -> ChatOutcome:
    """会話履歴を送り、BOT の応答を返す。失敗しても例外は投げず ChatOutcome に入れる。"""
    model = str(spec.models.get("chat", ""))
    outcome = ChatOutcome(model=model)
    fn = PROVIDERS.get(spec.provider)
    if fn is None:
        outcome.error = f"未対応のプロバイダーです: {spec.provider}"
        return outcome
    api_key = api_keys.get(spec.provider)
    if not api_key:
        outcome.error = f"{spec.provider} の API キーが設定されていません"
        return outcome
    if not model:
        outcome.error = "models.chat が設定されていません"
        return outcome

    client, exchanges = capturing_client()
    outcome.exchanges = exchanges
    try:
        with client:
            outcome.text = fn(spec, history, api_key, client)
    except Exception as e:  # noqa: BLE001 - エラーは保存して止めるため、種類を問わず受け取る
        outcome.error = f"{type(e).__name__}: {e}"
        outcome.model_unavailable = any(check(e) for check in _NOT_FOUND_CHECKS)
    return outcome
