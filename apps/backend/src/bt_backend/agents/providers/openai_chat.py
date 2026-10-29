"""OpenAI と、OpenAI 互換の OpenRouter。"""

from collections.abc import Sequence
from typing import Any

import httpx2
import openai

from bt_backend.agents.params import call_with_params
from bt_backend.agents.types import BotSpec, ChatTurn

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_request(spec: BotSpec, history: Sequence[ChatTurn]) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    system = spec.settings.get("system_prompt")
    if system:
        messages.append({"role": "system", "content": system})
    messages += [{"role": t.role, "content": t.content} for t in history]
    params = dict(spec.settings.get("params") or {})
    return {"model": spec.models["chat"], "messages": messages, **params}


def _chat(
    spec: BotSpec,
    history: Sequence[ChatTurn],
    api_key: str,
    http: httpx2.Client,
    base_url: str | None,
) -> str:
    client = openai.OpenAI(api_key=api_key, base_url=base_url, http_client=http, max_retries=0)
    response = call_with_params(client.chat.completions.create, build_request(spec, history))
    return str(response.choices[0].message.content or "")


def chat_openai(
    spec: BotSpec, history: Sequence[ChatTurn], api_key: str, http: httpx2.Client
) -> str:
    return _chat(spec, history, api_key, http, None)


def chat_openrouter(
    spec: BotSpec, history: Sequence[ChatTurn], api_key: str, http: httpx2.Client
) -> str:
    return _chat(spec, history, api_key, http, OPENROUTER_BASE_URL)


def is_not_found(e: Exception) -> bool:
    return isinstance(e, openai.NotFoundError)
