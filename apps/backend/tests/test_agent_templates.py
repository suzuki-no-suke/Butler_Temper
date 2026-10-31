import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, json_response
from tests.test_api import _create_bot
from tests.test_dialogues import _llm_by_model, _start


def _recording(sent: list[dict[str, Any]]) -> Handler:
    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        sent.append(body)
        return json_response(200, anthropic_message("応答", body["model"]))

    return handler


def _template(client: TestClient, name: str, content: str) -> int:
    r = client.post("/api/agent-templates", json={"name": name, "content": content})
    assert r.status_code == 200, r.text
    template_id: int = r.json()["id"]
    return template_id


def _version(client: TestClient, template_id: int, content: str) -> None:
    r = client.post(f"/api/agent-templates/{template_id}/versions", json={"content": content})
    assert r.status_code == 200, r.text


def _conversation(client: TestClient, bot_id: int) -> Any:
    return client.post("/api/conversations", json={"bot_id": bot_id})


def test_agent_templates_are_separate_from_dialogue_templates(client: TestClient) -> None:
    template_id = _template(client, "口調", "江戸っ子\r\nで話す\x07")
    _version(client, template_id, "丁寧に話す")
    detail = client.get(f"/api/agent-templates/{template_id}").json()
    assert detail["latest_version"] == 2
    # 保存するときにサニタイズする
    assert detail["versions"][0]["content"] == "江戸っ子\nで話す"
    assert client.get("/api/templates").json() == []
    r = client.post("/api/agent-templates", json={"name": "口調", "content": "x"})
    assert r.status_code == 409


def test_conversation_fixes_agent_templates_at_start(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    sent: list[dict[str, Any]] = []
    llm(_recording(sent))
    template_id = _template(client, "口調", '江戸っ子で "話す"\n短く')
    bot_id = _create_bot(client, system_prompt="執事です。{{agent_template:口調}}")
    first = _conversation(client, bot_id).json()
    _version(client, template_id, "丁寧に話す")
    second = _conversation(client, bot_id).json()

    client.post(f"/api/conversations/{first['id']}/messages", json={"content": "a"})
    client.post(f"/api/conversations/{second['id']}/messages", json={"content": "b"})
    # 始めたときのバージョンで埋め込んだ設定で動く（改行や引用符もそのまま入る）
    assert sent[0]["system"] == '執事です。江戸っ子で "話す"\n短く'
    assert sent[1]["system"] == "執事です。丁寧に話す"

    settings = client.get(f"/api/conversations/{first['id']}/settings").json()
    assert settings["settings"]["system_prompt"] == "執事です。{{agent_template:口調}}"
    assert settings["resolved_settings"]["system_prompt"] == '執事です。江戸っ子で "話す"\n短く'
    assert [(t["name"], t["version"]) for t in settings["agent_templates"]] == [("口調", 1)]


def test_missing_agent_template_blocks_start(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    llm(_llm_by_model([]))
    bot_id = _create_bot(client, system_prompt="{{agent_template:無い}}")
    r = _conversation(client, bot_id)
    assert r.status_code == 409
    assert "無い" in r.json()["detail"]
    r = client.post("/api/parallel-conversations", json={"bot_id": bot_id})
    assert r.status_code == 409
    # 対話用テンプレートの書き方は、Agent テンプレートとしては扱わない
    bot_id = _create_bot(client, system_prompt="{{template:台本}}")
    assert _conversation(client, bot_id).status_code == 200


def test_dialogue_and_parallel_keep_fixed_agent_settings(
    client: TestClient, llm: Callable[[Handler], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[dict[str, Any]] = []
    llm(_llm_by_model(sent))
    template_id = _template(client, "口調", "江戸っ子")
    # _start が作る Agent の設定に、Agent テンプレートを入れる
    from tests import test_dialogues

    monkeypatch.setattr(
        test_dialogues,
        "_create_bot",
        lambda c, system_prompt="": _create_bot(c, system_prompt="執事。{{agent_template:口調}}"),
    )
    dialogue_id, _, _ = _start(client)
    _version(client, template_id, "丁寧")
    client.post(f"/api/dialogues/{dialogue_id}/turn")
    agent_call = next(b for b in sent if b["model"] == "claude-opus-5-5")
    assert agent_call["system"] == "執事。江戸っ子"
    settings = client.get(f"/api/dialogues/{dialogue_id}/settings").json()
    assert [(t["name"], t["version"]) for t in settings["bot"]["agent_templates"]] == [("口調", 1)]

    # 対話から写した並行会話と、採用した会話も、対話を始めたときの設定で動く
    speeches = client.get(f"/api/dialogues/{dialogue_id}").json()["messages"]
    agent_speech = next(m for m in speeches if m["speaker"] == "agent")
    parallel_id = client.post(
        f"/api/dialogues/{dialogue_id}/parallel", json={"message_id": agent_speech["id"]}
    ).json()["id"]
    sent.clear()
    client.post(
        f"/api/parallel-conversations/{parallel_id}/rounds", json={"content": "x", "count": 1}
    )
    assert sent[0]["system"] == "執事。江戸っ子"
    candidate = client.get(f"/api/parallel-conversations/{parallel_id}").json()["rounds"][0][
        "candidates"
    ][0]
    adopted = client.post(f"/api/parallel-candidates/{candidate['id']}/adopt").json()
    settings = client.get(f"/api/conversations/{adopted['id']}/settings").json()
    assert settings["resolved_settings"]["system_prompt"] == "執事。江戸っ子"
