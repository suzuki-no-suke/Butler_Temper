import json
from collections.abc import Callable
from typing import Any

import httpx2
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, json_response
from tests.test_api import _create_bot

CORE = "conversation-script-sonnet"


def _core(client: TestClient) -> dict[str, Any]:
    cores: list[dict[str, Any]] = client.get("/api/conversation-agents").json()
    return next(c for c in cores if c["id"] == CORE)


def _create_template(client: TestClient, name: str = "台本", content: str = "挨拶する") -> int:
    r = client.post("/api/templates", json={"name": name, "content": content})
    assert r.status_code == 200, r.text
    template_id: int = r.json()["id"]
    return template_id


def _create_conversation_bot(client: TestClient, prompt: str = "台本: {{template:台本}}") -> int:
    settings = {**_core(client)["default_settings"], "system_prompt": prompt}
    r = client.post(
        "/api/conversation-bots", json={"name": "主人役", "agent_id": CORE, "settings": settings}
    )
    assert r.status_code == 200, r.text
    bot_id: int = r.json()["id"]
    return bot_id


def _start(client: TestClient) -> tuple[int, int, int]:
    _create_template(client)
    cbot_id = _create_conversation_bot(client)
    bot_id = _create_bot(client, system_prompt="執事です")
    r = client.post("/api/dialogues", json={"conversation_bot_id": cbot_id, "bot_id": bot_id})
    assert r.status_code == 200, r.text
    dialogue_id: int = r.json()["id"]
    return dialogue_id, cbot_id, bot_id


def _llm_by_model(sent: list[dict[str, Any]], agent_status: int = 200) -> Handler:
    """会話用エージェント（Sonnet）と Agent（Opus）に、別々の返答をする。"""

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        sent.append(body)
        if body["model"] == "claude-sonnet-5-5":
            return json_response(200, anthropic_message(f"主人の発言{len(sent)}", body["model"]))
        if agent_status != 200:
            return json_response(agent_status, {"type": "error", "error": {"message": "x"}})
        return json_response(200, anthropic_message(f"執事の応答{len(sent)}", body["model"]))

    return handler


def test_conversation_agents_are_separate_from_agents(client: TestClient) -> None:
    agent_ids = {a["id"] for a in client.get("/api/agents").json()}
    core_ids = {c["id"] for c in client.get("/api/conversation-agents").json()}
    assert core_ids == {"conversation-script-sonnet", "conversation-script-opus"}
    assert not agent_ids & core_ids
    # 互いの AgentCore では作れない
    r = client.post(
        "/api/conversation-bots",
        json={"name": "x", "agent_id": "claude-simple-opus", "settings": {}},
    )
    assert r.status_code == 400
    r = client.post("/api/bots", json={"name": "x", "agent_id": CORE, "settings": {}})
    assert r.status_code == 400
    cbot_id = _create_conversation_bot(client)
    assert client.get("/api/bots").json() == []
    assert [b["id"] for b in client.get("/api/conversation-bots").json()] == [cbot_id]


def test_conversation_bot_versions_and_fork(client: TestClient) -> None:
    cbot_id = _create_conversation_bot(client, prompt="v1")
    settings = client.get(f"/api/conversation-bots/{cbot_id}").json()["versions"][0]["settings"]
    r = client.post(
        f"/api/conversation-bots/{cbot_id}/versions",
        json={"settings": {**settings, "system_prompt": "v2"}},
    )
    assert r.json()["version"] == 2
    r = client.post(
        f"/api/conversation-bots/{cbot_id}/fork",
        json={"name": "主人役2", "settings": settings, "base_version": 1},
    )
    assert r.status_code == 200
    assert r.json()["forked_from_bot_name"] == "主人役"
    assert r.json()["latest_version"] == 1


def test_template_is_sanitized_and_versioned(client: TestClient) -> None:
    template_id = _create_template(client, content="一行目\r\n二\x00行目\t終わり\x1b")
    r = client.post(f"/api/templates/{template_id}/versions", json={"content": "二つ目"})
    assert r.json()["version"] == 2
    detail = client.get(f"/api/templates/{template_id}").json()
    assert [v["content"] for v in detail["versions"]] == ["一行目\n二行目\t終わり", "二つ目"]
    assert client.post("/api/templates", json={"name": "台本", "content": ""}).status_code == 409
    assert client.post("/api/templates", json={"name": "a}b", "content": ""}).status_code == 422


def test_dialogue_turn(client: TestClient, llm: Callable[[Handler], None]) -> None:
    sent: list[dict[str, Any]] = []
    llm(_llm_by_model(sent))
    dialogue_id, _, _ = _start(client)

    r = client.post(f"/api/dialogues/{dialogue_id}/turn")
    assert r.status_code == 200, r.text
    first = r.json()
    assert [(m["speaker"], m["content"]) for m in first] == [
        ("conversation", "主人の発言1"),
        ("agent", "執事の応答2"),
    ]
    # 会話用エージェントにはテンプレートを埋め込んだプロンプトと、始めの指示が行く
    assert sent[0]["system"] == "台本: 挨拶する"
    assert sent[0]["messages"][0]["role"] == "user"
    # Agent には、会話用エージェントの発言が利用者の発言として行く
    assert sent[1]["system"] == "執事です"
    assert sent[1]["messages"] == [{"role": "user", "content": "主人の発言1"}]

    client.post(f"/api/dialogues/{dialogue_id}/turn")
    # 会話用エージェントから見ると、自分の発言が assistant、Agent の発言が user
    assert [m["role"] for m in sent[2]["messages"]] == ["user", "assistant", "user"]
    assert sent[2]["messages"][1:] == [
        {"role": "assistant", "content": "主人の発言1"},
        {"role": "user", "content": "執事の応答2"},
    ]
    assert [m["role"] for m in sent[3]["messages"]] == ["user", "assistant", "user"]

    detail = client.get(f"/api/dialogues/{dialogue_id}").json()
    assert detail["message_count"] == 4
    assert detail["preview"] == "主人の発言1"
    assert detail["templates"][0]["name"] == "台本"
    raw = client.get(f"/api/raw-calls/{first[0]['raw_call_id']}").json()
    assert raw["dialogue_id"] == dialogue_id
    assert raw["conversation_id"] is None
    assert raw["agent_id"] == CORE
    # エージェント間対話は、Agent の会話の一覧には出ない
    assert client.get("/api/conversations").json() == []


def test_templates_are_fixed_at_start(client: TestClient, llm: Callable[[Handler], None]) -> None:
    sent: list[dict[str, Any]] = []
    llm(_llm_by_model(sent))
    dialogue_id, _, _ = _start(client)
    template_id = client.get("/api/templates").json()[0]["id"]
    client.post(f"/api/templates/{template_id}/versions", json={"content": "直した台本"})
    client.post(f"/api/dialogues/{dialogue_id}/turn")
    assert sent[0]["system"] == "台本: 挨拶する"
    settings = client.get(f"/api/dialogues/{dialogue_id}/settings").json()
    assert settings["templates"] == [
        {"name": "台本", "template_id": template_id, "version": 1, "content": "挨拶する"}
    ]
    assert settings["bot"]["settings"]["system_prompt"] == "執事です"


def test_missing_template_blocks_start(client: TestClient) -> None:
    cbot_id = _create_conversation_bot(client, prompt="{{template:無い}}")
    bot_id = _create_bot(client)
    r = client.post("/api/dialogues", json={"conversation_bot_id": cbot_id, "bot_id": bot_id})
    assert r.status_code == 409
    assert "無い" in r.json()["detail"]


def test_both_speeches_can_be_rated(client: TestClient, llm: Callable[[Handler], None]) -> None:
    llm(_llm_by_model([]))
    dialogue_id, _, _ = _start(client)
    messages = client.post(f"/api/dialogues/{dialogue_id}/turn").json()
    for m, rating in zip(messages, ["GOOD", "BAD"], strict=True):
        r = client.put(f"/api/dialogue-messages/{m['id']}/comment", json={"rating": rating})
        assert r.status_code == 200
    r = client.post(f"/api/dialogues/{dialogue_id}/comments", json={"text": "全体"})
    assert r.status_code == 200
    detail = client.get(f"/api/dialogues/{dialogue_id}").json()
    assert [m["comment"]["rating"] for m in detail["messages"]] == ["GOOD", "BAD"]
    assert [c["text"] for c in detail["comments"]] == ["全体"]


def test_agent_error_stops_and_resume(client: TestClient, llm: Callable[[Handler], None]) -> None:
    sent: list[dict[str, Any]] = []
    llm(_llm_by_model(sent))
    dialogue_id, _, _ = _start(client)
    client.post(f"/api/dialogues/{dialogue_id}/turn")

    llm(_llm_by_model(sent, agent_status=500))
    messages = client.post(f"/api/dialogues/{dialogue_id}/turn").json()
    assert [(m["speaker"], m["role"]) for m in messages] == [
        ("conversation", "speech"),
        ("agent", "error"),
    ]
    detail = client.get(f"/api/dialogues/{dialogue_id}").json()
    assert detail["status"] == "stopped"
    assert client.post(f"/api/dialogues/{dialogue_id}/turn").status_code == 409

    resumed = client.post(f"/api/dialogues/{dialogue_id}/resume").json()
    assert resumed["resumed_from_id"] == dialogue_id
    # 応答を得られなかった会話用エージェントの発言とエラーは引き継がない
    assert resumed["message_count"] == 2
    assert resumed["templates"] == detail["templates"]
    llm(_llm_by_model(sent))
    assert client.post(f"/api/dialogues/{resumed['id']}/turn").status_code == 200
