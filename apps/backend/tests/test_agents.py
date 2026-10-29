import json
from collections.abc import Callable

import httpx2

from bt_backend.agents import BotSpec, ChatTurn, run_chat
from tests.conftest import Handler, anthropic_message, anthropic_not_found, json_response

KEYS = {
    "anthropic": "secret-a",
    "openai": "secret-o",
    "gemini": "secret-g",
    "openrouter": "secret-r",
}
HISTORY = [ChatTurn(role="user", content="こんにちは")]


def _spec(provider: str, **settings: object) -> BotSpec:
    return BotSpec(provider=provider, models={"chat": "m-20260101"}, settings=dict(settings))


def test_anthropic_records_raw_exchange(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(200, anthropic_message("やあ")))
    spec = _spec("anthropic", system_prompt="執事", params={"temperature": 0.5})
    outcome = run_chat(spec, HISTORY, KEYS)
    assert outcome.error is None
    assert outcome.text == "やあ"
    [ex] = outcome.exchanges
    assert ex["request"]["system"] == "執事"
    assert ex["request"]["temperature"] == 0.5
    assert ex["request"]["max_tokens"] == 1024
    assert ex["response"]["content"][0]["text"] == "やあ"
    assert "secret-a" not in json.dumps(ex)


def test_anthropic_not_found_marks_model_unavailable(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(404, anthropic_not_found()))
    outcome = run_chat(_spec("anthropic"), HISTORY, KEYS)
    assert outcome.error is not None
    assert outcome.model_unavailable
    assert outcome.exchanges[0]["status"] == 404


def test_server_error_is_not_model_unavailable(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(500, {"type": "error", "error": {"type": "api_error"}}))
    outcome = run_chat(_spec("anthropic"), HISTORY, KEYS)
    assert outcome.error is not None
    assert not outcome.model_unavailable
    # SDK の自動リトライはしない
    assert len(outcome.exchanges) == 1


def test_openrouter_uses_openai_format(llm: Callable[[Handler], None]) -> None:
    seen: list[httpx2.Request] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.append(req)
        return json_response(
            200,
            {
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "m-20260101",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
            },
        )

    llm(handler)
    outcome = run_chat(_spec("openrouter", system_prompt="sys"), HISTORY, KEYS)
    assert outcome.text == "ok"
    assert seen[0].url.host == "openrouter.ai"
    assert outcome.exchanges[0]["request"]["messages"][0] == {"role": "system", "content": "sys"}


def test_gemini(llm: Callable[[Handler], None]) -> None:
    llm(
        lambda req: json_response(
            200,
            {"candidates": [{"content": {"role": "model", "parts": [{"text": "gem"}]}}]},
        )
    )
    outcome = run_chat(_spec("gemini", system_prompt="sys"), HISTORY, KEYS)
    assert outcome.error is None, outcome.error
    assert outcome.text == "gem"
    assert "secret-g" not in json.dumps(outcome.exchanges)


def test_missing_api_key() -> None:
    outcome = run_chat(_spec("openai"), HISTORY, {})
    assert outcome.error is not None
    assert outcome.exchanges == []
