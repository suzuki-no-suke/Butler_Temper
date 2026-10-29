from collections.abc import Sequence
from typing import Any

import anthropic
import httpx2

from bt_backend.agents.params import call_with_params
from bt_backend.agents.types import BotSpec, ChatTurn

DEFAULT_MAX_TOKENS = 1024


def build_request(spec: BotSpec, history: Sequence[ChatTurn]) -> dict[str, Any]:
    params = dict(spec.settings.get("params") or {})
    params.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
    request: dict[str, Any] = {
        "model": spec.models["chat"],
        "messages": [{"role": t.role, "content": t.content} for t in history],
        **params,
    }
    system = spec.settings.get("system_prompt")
    if system:
        request["system"] = system
    return request


def chat(spec: BotSpec, history: Sequence[ChatTurn], api_key: str, http: httpx2.Client) -> str:
    client = anthropic.Anthropic(api_key=api_key, http_client=http, max_retries=0)
    response = call_with_params(client.messages.create, build_request(spec, history))
    return "".join(block.text for block in response.content if block.type == "text")


def is_not_found(e: Exception) -> bool:
    return isinstance(e, anthropic.NotFoundError)
