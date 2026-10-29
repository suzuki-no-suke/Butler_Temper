from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, json_response
from tests.test_api import _create_bot


def _conversation_with_reply(client: TestClient, llm: Callable[[Handler], None]) -> dict[str, Any]:
    llm(lambda req: json_response(200, anthropic_message("はい")))
    bot_id = _create_bot(client)
    conv = client.post("/api/conversations", json={"bot_id": bot_id}).json()
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"})
    detail: dict[str, Any] = client.get(f"/api/conversations/{conv['id']}").json()
    return detail


def test_message_comment_is_one_per_reply(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    detail = _conversation_with_reply(client, llm)
    user, reply = detail["messages"]
    assert reply["comment"] is None

    r = client.put(f"/api/messages/{reply['id']}/comment", json={"rating": "GOOD", "text": "良い"})
    assert r.status_code == 200, r.text
    r = client.put(f"/api/messages/{reply['id']}/comment", json={"rating": "BAD", "text": "直す"})
    assert r.json()["rating"] == "BAD"
    reply = client.get(f"/api/conversations/{detail['id']}").json()["messages"][1]
    assert (reply["comment"]["rating"], reply["comment"]["text"]) == ("BAD", "直す")

    client.delete(f"/api/messages/{reply['id']}/comment")
    reply = client.get(f"/api/conversations/{detail['id']}").json()["messages"][1]
    assert reply["comment"] is None


def test_message_comment_rejects_user_message_and_bad_rating(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    detail = _conversation_with_reply(client, llm)
    user, reply = detail["messages"]
    r = client.put(f"/api/messages/{user['id']}/comment", json={"rating": "GOOD"})
    assert r.status_code == 400
    r = client.put(f"/api/messages/{reply['id']}/comment", json={"rating": "GREAT"})
    assert r.status_code == 422


def test_conversation_comments_can_be_many(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    detail = _conversation_with_reply(client, llm)
    cid = detail["id"]
    client.post(f"/api/conversations/{cid}/comments", json={"rating": "FINE", "text": "一つ目"})
    second = client.post(f"/api/conversations/{cid}/comments", json={"text": "評価なし"}).json()
    assert second["rating"] is None
    assert client.post(f"/api/conversations/{cid}/comments", json={"text": " "}).status_code == 400
    comments = client.get(f"/api/conversations/{cid}").json()["comments"]
    assert [c["text"] for c in comments] == ["一つ目", "評価なし"]
    client.delete(f"/api/conversation-comments/{second['id']}")
    comments = client.get(f"/api/conversations/{cid}").json()["comments"]
    assert [c["text"] for c in comments] == ["一つ目"]


def test_conversation_settings_shows_fixed_version(client: TestClient) -> None:
    bot_id = _create_bot(client, system_prompt="v1")
    conv = client.post("/api/conversations", json={"bot_id": bot_id}).json()
    settings = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    client.post(
        f"/api/bots/{bot_id}/versions", json={"settings": {**settings, "system_prompt": "v2"}}
    )
    shown = client.get(f"/api/conversations/{conv['id']}/settings").json()
    assert shown["version"] == 1
    assert shown["settings"]["system_prompt"] == "v1"
    assert shown["agent_id"] == "claude-simple-opus"
