from collections.abc import Sequence
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types

from bt_backend.agents.types import BotSpec, ChatTurn


def build_request(spec: BotSpec, history: Sequence[ChatTurn]) -> dict[str, Any]:
    params = dict(spec.settings.get("params") or {})
    system = spec.settings.get("system_prompt")
    if system:
        params["system_instruction"] = system
    return {
        "model": spec.models["chat"],
        "contents": [
            types.Content(
                role="model" if t.role == "assistant" else "user",
                parts=[types.Part(text=t.content)],
            )
            for t in history
        ],
        "config": types.GenerateContentConfig(**params),
    }


def chat(spec: BotSpec, history: Sequence[ChatTurn], api_key: str, http: httpx2.Client) -> str:
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(httpx_client=http))
    response = client.models.generate_content(**build_request(spec, history))
    return response.text or ""


def is_not_found(e: Exception) -> bool:
    return isinstance(e, errors.ClientError) and e.code == 404
