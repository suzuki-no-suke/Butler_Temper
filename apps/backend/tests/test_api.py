import json
from collections.abc import Callable
from pathlib import Path

import httpx2
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, anthropic_not_found, json_response


def _create_bot(client: TestClient) -> int:
    r = client.post(
        "/api/bots",
        json={
            "name": "執事",
            "provider": "anthropic",
            "models": {"chat": "claude-test-20260101"},
            "settings": {"system_prompt": "v1"},
        },
    )
    assert r.status_code == 200, r.text
    bot_id: int = r.json()["id"]
    return bot_id


def test_bot_versions(client: TestClient) -> None:
    bot_id = _create_bot(client)
    r = client.post(f"/api/bots/{bot_id}/versions", json={"settings": {"system_prompt": "v2"}})
    assert r.json()["version"] == 2
    bot = client.get(f"/api/bots/{bot_id}").json()
    assert bot["latest_version"] == 2
    assert [v["settings"]["system_prompt"] for v in bot["versions"]] == ["v1", "v2"]


def test_bot_requires_chat_model(client: TestClient) -> None:
    r = client.post("/api/bots", json={"name": "x", "provider": "anthropic", "models": {}})
    assert r.status_code == 400


def test_conversation_is_fixed_to_version(
    client: TestClient, llm: Callable[[Handler], None], data_dir: Path
) -> None:
    sent: list[str] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(req.content)["system"])
        return json_response(200, anthropic_message("はい"))

    llm(handler)
    bot_id = _create_bot(client)
    conv = client.post("/api/conversations", json={"bot_id": bot_id}).json()
    assert conv["bot_version"] == 1
    client.post(f"/api/bots/{bot_id}/versions", json={"settings": {"system_prompt": "v2"}})

    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"})
    assert r.status_code == 200, r.text
    user, reply = r.json()
    assert (user["role"], reply["role"], reply["content"]) == ("user", "assistant", "はい")
    assert sent == ["v1"]

    raw = client.get(f"/api/raw-calls/{reply['raw_call_id']}").json()
    assert raw["exchanges"][0]["request"]["messages"] == [{"role": "user", "content": "やあ"}]
    assert (data_dir / "agent_snapshots" / f"{raw['source_hash']}.zip").exists()

    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "続き"})
    raw2 = client.get(f"/api/raw-calls/{reply['raw_call_id'] + 1}").json()
    assert [m["role"] for m in raw2["exchanges"][0]["request"]["messages"]] == [
        "user",
        "assistant",
        "user",
    ]


def test_error_stops_conversation(client: TestClient, llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(500, {"type": "error", "error": {"type": "api_error"}}))
    bot_id = _create_bot(client)
    conv = client.post("/api/conversations", json={"bot_id": bot_id}).json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"})
    assert r.json()[1]["role"] == "error"
    assert client.get(f"/api/conversations/{conv['id']}").json()["status"] == "stopped"
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "再送"})
    assert r.status_code == 409
    # BOT 自体は止めない
    assert client.post("/api/conversations", json={"bot_id": bot_id}).status_code == 200


def test_missing_model_stops_bot(client: TestClient, llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(404, anthropic_not_found()))
    bot_id = _create_bot(client)
    conv = client.post("/api/conversations", json={"bot_id": bot_id}).json()
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"})
    assert client.get(f"/api/bots/{bot_id}").json()["unavailable_reason"]
    assert client.post("/api/conversations", json={"bot_id": bot_id}).status_code == 409
