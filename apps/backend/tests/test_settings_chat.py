import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from bt_backend.agents.assist import settings_chat
from tests.test_api import _create_bot

Responder = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> Callable[[Responder], list[str]]:
    """設定変更チャットの LLM を FunctionModel に差し替える。送られたプロンプトを返す。"""

    def install(responder: Responder) -> list[str]:
        prompts: list[str] = []
        real = settings_chat.propose_settings

        def wrapped(
            agent_id: str,
            current: str,
            history: list[settings_chat.ChatLine],
            request: str,
            api_key: str | None,
        ) -> settings_chat.SettingsProposal:
            prompts.append(request)
            return real(agent_id, current, history, request, api_key, FunctionModel(responder))

        monkeypatch.setattr("bt_backend.api.settings_chat.propose_settings", wrapped)
        return prompts

    return install


def _answer(info: AgentInfo, output: dict[str, Any]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])


def test_settings_chat_returns_proposal(
    client: TestClient, fake_ai: Callable[[Responder], list[str]]
) -> None:
    bot_id = _create_bot(client, system_prompt="v1")
    current = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    proposed = {**current, "system_prompt": "もっと砕けた口調の執事"}
    fake_ai(
        lambda messages, info: _answer(info, {"reply": "口調を変えました", "settings": proposed})
    )

    r = client.post(
        f"/api/bots/{bot_id}/settings-chat",
        json={"message": "口調を砕けた感じに", "current_settings": json.dumps(current)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposed_settings"] == proposed
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["content"] == "口調を変えました"
    # 案は保存しない（バージョンは増えない）
    assert client.get(f"/api/bots/{bot_id}").json()["latest_version"] == 1

    history = client.get(f"/api/bots/{bot_id}/settings-chat").json()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_settings_chat_retries_invalid_settings(
    client: TestClient, fake_ai: Callable[[Responder], list[str]]
) -> None:
    bot_id = _create_bot(client)
    current = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    calls: list[int] = []

    def responder(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        if len(calls) == 1:
            # 知らない項目を入れた案は、PydanticAI がやり直させる
            return _answer(info, {"reply": "x", "settings": {**current, "typo": 1}})
        return _answer(info, {"reply": "直しました", "settings": {**current, "max_tokens": 100}})

    fake_ai(responder)
    r = client.post(
        f"/api/bots/{bot_id}/settings-chat",
        json={"message": "短く", "current_settings": json.dumps(current)},
    )
    assert len(calls) == 2
    assert r.json()["proposed_settings"]["max_tokens"] == 100


def test_settings_chat_without_change(
    client: TestClient, fake_ai: Callable[[Responder], list[str]]
) -> None:
    bot_id = _create_bot(client)
    fake_ai(lambda messages, info: _answer(info, {"reply": "今の設定で大丈夫です"}))
    r = client.post(
        f"/api/bots/{bot_id}/settings-chat",
        json={"message": "このままでいい？", "current_settings": "{書きかけ"},
    )
    assert r.json()["proposed_settings"] is None


def test_settings_chat_passes_history_and_current_settings(
    client: TestClient, fake_ai: Callable[[Responder], list[str]]
) -> None:
    bot_id = _create_bot(client)
    seen: list[str] = []

    def responder(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(str(messages[0].parts[-1].content))  # type: ignore[union-attr]
        return _answer(info, {"reply": f"返答{len(seen)}"})

    fake_ai(responder)
    for text in ("一つ目の要望", "二つ目の要望"):
        client.post(
            f"/api/bots/{bot_id}/settings-chat",
            json={"message": text, "current_settings": '{"marker": "編集中"}'},
        )
    assert "編集中" in seen[1]
    assert "一つ目の要望" in seen[1] and "返答1" in seen[1]
    assert "二つ目の要望" in seen[1]

    client.delete(f"/api/bots/{bot_id}/settings-chat")
    assert client.get(f"/api/bots/{bot_id}/settings-chat").json() == []


def test_settings_chat_error_is_recorded(client: TestClient) -> None:
    # API キーが無いので失敗し、エラーとして残る
    bot_id = _create_bot(client)
    from bt_backend import config

    config.get_settings().anthropic_api_key = None
    r = client.post(
        f"/api/bots/{bot_id}/settings-chat", json={"message": "x", "current_settings": "{}"}
    )
    assert r.status_code == 200
    assert r.json()["messages"][1]["role"] == "error"
    assert r.json()["proposed_settings"] is None
