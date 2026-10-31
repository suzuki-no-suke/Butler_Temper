import json
import random
import threading
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.conftest import Handler, anthropic_message, json_response
from tests.test_api import _create_bot
from tests.test_dialogues import _llm_by_model, _start


@pytest.fixture(autouse=True)
def fixed_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    from bt_backend.agents import kamidanomi
    from bt_backend.simulators import chance

    monkeypatch.setattr(chance, "rng", random.Random(1))
    monkeypatch.setattr(kamidanomi, "rng", random.Random(1))


def _counting(sent: list[dict[str, Any]]) -> Handler:
    """呼ばれるたびに違う応答を返す（候補は並行に作られるので、数え方は排他にする）。"""
    lock = threading.Lock()

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        with lock:
            sent.append(body)
            n = len(sent)
        return json_response(200, anthropic_message(f"応答{n}", body["model"]))

    return handler


def _chat(client: TestClient, bot_id: int, *texts: str) -> tuple[int, list[dict[str, Any]]]:
    conv_id = int(client.post("/api/conversations", json={"bot_id": bot_id}).json()["id"])
    for text in texts:
        r = client.post(f"/api/conversations/{conv_id}/messages", json={"content": text})
        assert r.status_code == 200, r.text
    messages: list[dict[str, Any]] = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    return conv_id, messages


def _round(client: TestClient, parallel_id: int, content: str, count: int) -> None:
    r = client.post(
        f"/api/parallel-conversations/{parallel_id}/rounds",
        json={"content": content, "count": count},
    )
    assert r.status_code == 200, r.text


def test_parallel_from_conversation_and_adopt(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    sent: list[dict[str, Any]] = []
    llm(_counting(sent))
    bot_id = _create_bot(client, system_prompt="執事です")
    conv_id, messages = _chat(client, bot_id, "おはよう", "今日の予定は？")

    # 分かれる位置は Agent の発言だけ
    r = client.post(
        f"/api/conversations/{conv_id}/parallel", json={"message_id": messages[0]["id"]}
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/conversations/{conv_id}/parallel", json={"message_id": messages[1]["id"]}
    )
    assert r.status_code == 200, r.text
    parallel_id = r.json()["id"]

    sent.clear()
    _round(client, parallel_id, "お茶をください", 3)
    _round(client, parallel_id, "紅茶をください", 2)
    detail = client.get(f"/api/parallel-conversations/{parallel_id}").json()
    # 分かれる位置までの発言を写して持つ（RAW・状態も）
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "おはよう"),
        ("assistant", "応答1"),
    ]
    assert detail["messages"][1]["raw_call_id"] == messages[1]["raw_call_id"]
    assert detail["round_count"] == 2
    first, second = detail["rounds"]
    assert first["content"] == "お茶をください"
    assert [c["status"] for c in first["candidates"]] == ["succeeded"] * 3
    assert len(second["candidates"]) == 2
    texts = {c["text"] for r in detail["rounds"] for c in r["candidates"]}
    assert len(texts) == 5
    # 候補には、分かれる位置までの会話と、その回の入力が行く
    for body in sent:
        assert body["messages"][:2] == [
            {"role": "user", "content": "おはよう"},
            {"role": "assistant", "content": "応答1"},
        ]
        assert body["messages"][2]["content"] in ("お茶をください", "紅茶をください")
    candidate = first["candidates"][1]
    raw = client.get(f"/api/raw-calls/{candidate['raw_call_id']}").json()
    assert raw["parallel_candidate_id"] == candidate["id"]
    assert raw["conversation_id"] is None

    # 同じ候補を何度でも採用でき、そのたびに新しい会話になる
    adopted = [
        client.post(f"/api/parallel-candidates/{candidate['id']}/adopt").json() for _ in range(2)
    ]
    assert adopted[0]["id"] != adopted[1]["id"]
    assert adopted[0]["parallel_conversation_id"] == parallel_id
    assert adopted[0]["parallel_candidate_id"] == candidate["id"]
    conversation = client.get(f"/api/conversations/{adopted[0]['id']}").json()
    assert [(m["role"], m["content"]) for m in conversation["messages"]] == [
        ("user", "おはよう"),
        ("assistant", "応答1"),
        ("user", "お茶をください"),
        ("assistant", candidate["text"]),
    ]
    detail = client.get(f"/api/parallel-conversations/{parallel_id}").json()
    assert detail["rounds"][0]["candidates"][1]["conversation_ids"] == [a["id"] for a in adopted]

    # 採用した会話は、そのまま続けられる
    r = client.post(f"/api/conversations/{adopted[0]['id']}/messages", json={"content": "続き"})
    assert r.status_code == 200, r.text
    # 元の会話は変わらない
    assert len(client.get(f"/api/conversations/{conv_id}").json()["messages"]) == 4
    listing = client.get("/api/parallel-conversations").json()
    assert [p["id"] for p in listing] == [parallel_id]
    assert listing[0]["preview"] == "応答1"


def test_parallel_from_dialogue_uses_own_input(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    sent: list[dict[str, Any]] = []
    llm(_llm_by_model(sent))
    dialogue_id, _, _ = _start(client)
    client.post(f"/api/dialogues/{dialogue_id}/turn")
    speeches = client.get(f"/api/dialogues/{dialogue_id}").json()["messages"]
    agent_speech = next(m for m in speeches if m["speaker"] == "agent")
    r = client.post(
        f"/api/dialogues/{dialogue_id}/parallel", json={"message_id": agent_speech["id"]}
    )
    assert r.status_code == 200, r.text
    parallel_id = r.json()["id"]
    assert r.json()["source_kind"] == "dialogue"

    sent.clear()
    _round(client, parallel_id, "私が話します", 2)
    detail = client.get(f"/api/parallel-conversations/{parallel_id}").json()
    # 会話用エージェントの発言は利用者の発言として写す
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "主人の発言1"),
        ("assistant", "執事の応答2"),
    ]
    # 候補を作るのは Agent だけ（会話用エージェントは呼ばない）
    assert {b["model"] for b in sent} == {"claude-opus-5-5"}
    assert sent[0]["messages"][-1] == {"role": "user", "content": "私が話します"}
    assert [c["status"] for c in detail["rounds"][0]["candidates"]] == ["succeeded"] * 2


def test_candidate_simulations_are_kept_and_continuations_wait_for_adoption(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    from bt_backend.db import get_engine
    from bt_backend.models import ContinuationRecord

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        model = body["model"]
        if any(t["name"] == "report" for t in body.get("tools", [])):
            # 「またね」のときだけ、会話の終わりと判定する
            ending = body["messages"][0]["content"].endswith("お客さん: またね")
            report = {"stage": "closing", "ready": False, "ending": ending, "disclose": []}
            return json_response(
                200,
                {
                    **anthropic_message("", model),
                    "content": [{"type": "tool_use", "id": "t", "name": "report", "input": report}],
                    "stop_reason": "tool_use",
                },
            )
        words = body["system"].split("つづきの合言葉「")[-1].split("」")[0]
        return json_response(200, anthropic_message(f"合言葉は {words} でぃ", model))

    llm(handler)
    agent = next(a for a in client.get("/api/agents").json() if a["id"] == "kamidanomi-wanda")
    bot_id = client.post(
        "/api/bots",
        json={"name": "ワンダ", "agent_id": agent["id"], "settings": agent["default_settings"]},
    ).json()["id"]
    conv_id, messages = _chat(client, bot_id, "こんにちは")
    with Session(get_engine()) as session:
        before = len(session.exec(select(ContinuationRecord)).all())
    parallel_id = client.post(
        f"/api/conversations/{conv_id}/parallel", json={"message_id": messages[1]["id"]}
    ).json()["id"]
    _round(client, parallel_id, "またね", 2)
    candidates = client.get(f"/api/parallel-conversations/{parallel_id}").json()["rounds"][0][
        "candidates"
    ]
    assert [c["status"] for c in candidates] == ["succeeded"] * 2
    # 候補を作っただけでは、会話をまたぐ記録は書かない
    with Session(get_engine()) as session:
        assert len(session.exec(select(ContinuationRecord)).all()) == before
    adopted = client.post(f"/api/parallel-candidates/{candidates[0]['id']}/adopt").json()
    with Session(get_engine()) as session:
        records = session.exec(select(ContinuationRecord)).all()
        assert len(records) == before + 1
        assert records[-1].conversation_id == adopted["id"]


def test_candidate_simulation_runs_are_linked(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    lock = threading.Lock()
    calls: list[int] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        model = body["model"]
        last = body["messages"][-1]
        if body["messages"][-1]["role"] == "user" and last["content"] == "引く":
            with lock:
                calls.append(1)
            return json_response(
                200,
                {
                    **anthropic_message("", model),
                    "content": [{"type": "tool_use", "id": "t", "name": "omikuji", "input": {}}],
                    "stop_reason": "tool_use",
                },
            )
        return json_response(200, anthropic_message("吉でございます", model))

    llm(handler)
    agent = next(a for a in client.get("/api/agents").json() if a["id"] == "simulator-chat-sonnet")
    bot_id = client.post(
        "/api/bots",
        json={"name": "執事", "agent_id": agent["id"], "settings": agent["default_settings"]},
    ).json()["id"]
    conv_id, messages = _chat(client, bot_id, "こんにちは")
    parallel_id = client.post(
        f"/api/conversations/{conv_id}/parallel", json={"message_id": messages[1]["id"]}
    ).json()["id"]
    _round(client, parallel_id, "引く", 3)
    candidates = client.get(f"/api/parallel-conversations/{parallel_id}").json()["rounds"][0][
        "candidates"
    ]
    runs = client.get("/api/simulation-runs").json()
    assert len(runs) == 3
    for c in candidates:
        [part, _] = c["parts"]
        run = client.get(f"/api/simulation-runs/{part['simulation_run_id']}").json()
        assert run["caller"] == "parallel"
        assert run["parallel_candidate_id"] == c["id"]


def test_parallel_settings(client: TestClient) -> None:
    assert client.get("/api/parallel-settings").json() == {"concurrency": 3}
    r = client.put("/api/parallel-settings", json={"concurrency": 5})
    assert r.json() == {"concurrency": 5}
    assert client.put("/api/parallel-settings", json={"concurrency": 0}).status_code == 422
    assert client.get("/api/parallel-settings").json() == {"concurrency": 5}
