import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, anthropic_not_found, json_response


def _agent(client: TestClient, agent_id: str) -> dict[str, Any]:
    agents: list[dict[str, Any]] = client.get("/api/agents").json()
    return next(a for a in agents if a["id"] == agent_id)


def _create_bot(client: TestClient, system_prompt: str = "v1") -> int:
    settings = {**_agent(client, "claude-simple-opus")["default_settings"]}
    settings["system_prompt"] = system_prompt
    r = client.post(
        "/api/bots",
        json={"name": "執事", "agent_id": "claude-simple-opus", "settings": settings},
    )
    assert r.status_code == 200, r.text
    bot_id: int = r.json()["id"]
    return bot_id


def test_agents_have_description_and_defaults(client: TestClient) -> None:
    agent = _agent(client, "secret-keeper")
    assert agent["models"] == {"main": "claude-opus-5-5", "sub": "claude-haiku-5-5"}
    assert agent["default_settings"]["memory"]["recent_chars"] == 5000


def test_bot_versions_and_rename(client: TestClient) -> None:
    bot_id = _create_bot(client)
    settings = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    r = client.post(
        f"/api/bots/{bot_id}/versions", json={"settings": {**settings, "system_prompt": "v2"}}
    )
    assert r.json()["version"] == 2
    client.patch(f"/api/bots/{bot_id}", json={"name": "新しい名前"})
    bot = client.get(f"/api/bots/{bot_id}").json()
    assert bot["name"] == "新しい名前"
    assert bot["agent_name"] == "シンプル会話（Opus 5.5）"
    assert bot["latest_version"] == 2
    assert [v["settings"]["system_prompt"] for v in bot["versions"]] == ["v1", "v2"]


def test_settings_are_validated(client: TestClient) -> None:
    r = client.post(
        "/api/bots",
        json={"name": "x", "agent_id": "claude-simple-opus", "settings": {"typo": 1}},
    )
    assert r.status_code == 400
    assert "typo" in r.json()["detail"]
    r = client.post("/api/bots", json={"name": "x", "agent_id": "nope", "settings": {}})
    assert r.status_code == 400
    bot_id = _create_bot(client)
    r = client.post(f"/api/bots/{bot_id}/versions", json={"settings": {"max_tokens": 0}})
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
    settings = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    client.post(
        f"/api/bots/{bot_id}/versions", json={"settings": {**settings, "system_prompt": "v2"}}
    )

    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"})
    assert r.status_code == 200, r.text
    user, reply = r.json()
    assert (user["role"], reply["role"], reply["content"]) == ("user", "assistant", "はい")
    assert sent == ["v1"]

    raw = client.get(f"/api/raw-calls/{reply['raw_call_id']}").json()
    assert raw["agent_id"] == "claude-simple-opus"
    assert raw["exchanges"][0]["request"]["messages"] == [{"role": "user", "content": "やあ"}]
    assert (data_dir / "agent_snapshots" / f"{raw['source_hash']}.zip").exists()

    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "続き"})
    raw2 = client.get(f"/api/raw-calls/{reply['raw_call_id'] + 1}").json()
    assert [m["role"] for m in raw2["exchanges"][0]["request"]["messages"]] == [
        "user",
        "assistant",
        "user",
    ]


def test_secret_keeper_parts_and_state_are_saved(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        if body["model"] == "claude-opus-5-5":
            return json_response(200, anthropic_message("執事です"))
        judge = '{"disclose": true, "reason": "r", "message": "影です"}'
        return json_response(200, anthropic_message(judge, "claude-haiku-5-5"))

    llm(handler)
    settings = _agent(client, "secret-keeper")["default_settings"]
    bot = client.post(
        "/api/bots", json={"name": "館", "agent_id": "secret-keeper", "settings": settings}
    ).json()
    conv = client.post("/api/conversations", json={"bot_id": bot["id"]}).json()
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "ありがとう"})
    detail = client.get(f"/api/conversations/{conv['id']}").json()
    reply = detail["messages"][1]
    assert reply["content"] == "執事です"
    assert [p["speaker"] for p in reply["parts"]] == ["main", "sub"]
    assert detail["agent_state"]["disclosed"] is True
    assert reply["agent_state"]["disclosed"] is True


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


def test_seed_creates_one_bot_per_agent_only_once(client: TestClient) -> None:
    from bt_backend.seed import seed

    created = seed()
    assert created == len(client.get("/api/agents").json())
    assert seed() == 0
    names = {b["agent_id"] for b in client.get("/api/bots").json()}
    assert "secret-keeper" in names
