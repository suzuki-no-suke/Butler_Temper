"""LLM API の呼び出し。各社の SDK を直接使い、HTTP の中身をすべて記録する。"""

from collections.abc import Callable, Mapping
from typing import Any

import anthropic
import httpx2
import openai
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from bt_backend.agents.capture import capturing_client
from bt_backend.agents.params import call_with_params

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# テストで HTTP 通信を差し替えるためのもの
transport_override: httpx2.BaseTransport | None = None


class MissingApiKey(Exception):
    pass


def is_not_found(e: Exception) -> bool:
    """モデルが存在しないことを表す例外か。"""
    if isinstance(e, anthropic.NotFoundError | openai.NotFoundError):
        return True
    return isinstance(e, genai_errors.ClientError) and e.code == 404


class LlmSession:
    """1 ターンの間に行う LLM 呼び出しをまとめ、やり取りを記録する。"""

    def __init__(self, api_keys: Mapping[str, str | None]) -> None:
        self._api_keys = api_keys
        self.exchanges: list[dict[str, Any]] = []

    def _key(self, name: str) -> str:
        key = self._api_keys.get(name)
        if not key:
            raise MissingApiKey(f"{name} の API キーが設定されていません")
        return key

    def _call(self, label: str, fn: Callable[[httpx2.Client], Any]) -> Any:
        client, exchanges = capturing_client(transport=transport_override)
        try:
            with client:
                return fn(client)
        finally:
            for ex in exchanges:
                ex["label"] = label
            self.exchanges.extend(exchanges)

    def anthropic(self, label: str, request: dict[str, Any]) -> Any:
        """Messages API を呼び、SDK の Message を返す。"""
        key = self._key("anthropic")

        def call(http: httpx2.Client) -> Any:
            client = anthropic.Anthropic(api_key=key, http_client=http, max_retries=0)
            return call_with_params(client.messages.create, request)

        return self._call(label, call)

    def openai(self, label: str, request: dict[str, Any], *, openrouter: bool = False) -> Any:
        """Chat Completions API を呼ぶ。openrouter=True なら OpenRouter に送る。"""
        key = self._key("openrouter" if openrouter else "openai")
        base_url = OPENROUTER_BASE_URL if openrouter else None

        def call(http: httpx2.Client) -> Any:
            client = openai.OpenAI(api_key=key, base_url=base_url, http_client=http, max_retries=0)
            return call_with_params(client.chat.completions.create, request)

        return self._call(label, call)

    def gemini(self, label: str, request: dict[str, Any]) -> Any:
        """generate_content を呼ぶ。request は model / contents / config を持つ。"""
        key = self._key("gemini")

        def call(http: httpx2.Client) -> Any:
            options = genai_types.HttpOptions(httpx_client=http)
            client = genai.Client(api_key=key, http_options=options)
            return client.models.generate_content(**request)

        return self._call(label, call)


def anthropic_text(message: Any) -> str:
    return "".join(block.text for block in message.content if block.type == "text")
