import json
import random
import threading
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, json_response


@pytest.fixture(autouse=True)
def fixed_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    from bt_backend.simulators import chance

    monkeypatch.setattr(chance, "rng", random.Random(1))


def _run(client: TestClient, name: str, args: dict[str, Any], times: int = 1) -> Any:
    r = client.post(f"/api/simulators/{name}/runs", json={"args": args, "times": times})
    assert r.status_code == 200, r.text
    return r.json()


def _tool_use(name: str, args: dict[str, Any], model: str = "claude-sonnet-5-5") -> dict[str, Any]:
    return {
        **anthropic_message("", model),
        "content": [{"type": "tool_use", "id": "tu_1", "name": name, "input": args}],
        "stop_reason": "tool_use",
    }


def test_simulators_list_param_kinds(client: TestClient) -> None:
    simulators = {s["name"]: s for s in client.get("/api/simulators").json()}
    assert set(simulators) == {"omikuji", "dice", "dice_sum", "llm"}
    kinds = {p["name"]: p["kind"] for p in simulators["llm"]["params"]}
    assert kinds["prompt"] == "required"
    assert kinds["runs"] == "optional"
    assert kinds["model"] == "optional"
    assert kinds["llm_concurrency"] == "global"
    assert simulators["omikuji"]["params"] == []


def test_chance_simulators(client: TestClient) -> None:
    [dice] = _run(client, "dice", {"m": 6})
    assert dice["status"] == "succeeded"
    assert 1 <= dice["result"]["value"] <= 6
    assert dice["caller"] == "webui"
    assert dice["params"] == {"m": 6}

    [total] = _run(client, "dice_sum", {"n": 3, "m": 6})
    assert total["result"]["total"] == sum(total["detail"]["rolls"])
    assert len(total["detail"]["rolls"]) == 3

    runs = _run(client, "omikuji", {}, times=3)
    assert len(runs) == 3
    assert all(r["result"]["fortune"] in {"大吉", "中吉", "吉", "凶", "大凶"} for r in runs)
    listed = client.get("/api/simulation-runs", params={"simulator": "omikuji"}).json()
    assert [r["id"] for r in listed] == [r["id"] for r in reversed(runs)]


def test_missing_or_global_only_args_are_invalid(client: TestClient) -> None:
    [run] = _run(client, "dice_sum", {"n": 2})
    assert run["status"] == "invalid"
    assert run["params"] is None
    [run] = _run(client, "llm", {"prompt": "x", "llm_concurrency": 1})
    assert run["status"] == "invalid"


def test_llm_simulator_runs_and_merges(client: TestClient, llm: Callable[[Handler], None]) -> None:
    sent: list[dict[str, Any]] = []
    lock = threading.Lock()

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        with lock:
            sent.append(body)
            n = len(sent)
        if "tools" in body:
            return json_response(200, _tool_use("submit_result", {"result": "晴れが多い"}))
        if n == 1:
            return json_response(500, {"type": "error", "error": {"type": "api_error"}})
        return json_response(200, anthropic_message(f"晴れ{n}", body["model"]))

    llm(handler)
    client.put("/api/simulation-settings", json={"llm_runs": 3})
    [run] = _run(client, "llm", {"prompt": "明日の天気"})
    assert run["status"] == "succeeded", run["error"]
    assert run["result"] == {"result": "晴れが多い"}
    assert run["error_count"] == 1
    assert run["params"]["runs"] == 3
    assert run["params"]["model"] == "claude-sonnet-5-5"
    assert run["params"]["llm_concurrency"] == 5
    assert len(sent) == 4
    merge = sent[-1]
    assert merge["tool_choice"] == {"type": "tool", "name": "submit_result"}
    assert "明日の天気" in merge["messages"][0]["content"]

    detail = client.get(f"/api/simulation-runs/{run['id']}").json()
    labels = sorted(r["label"] for r in detail["raw_calls"])
    assert labels == ["merge", "run-1", "run-2", "run-3"]
    assert sum(1 for r in detail["raw_calls"] if r["error"]) == 1


def test_llm_simulator_fails_only_when_every_run_fails(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    llm(lambda req: json_response(500, {"type": "error", "error": {"type": "api_error"}}))
    [run] = _run(client, "llm", {"prompt": "x", "runs": 2})
    assert run["status"] == "failed"
    assert run["error_count"] == 2
    assert run["result"] is None


def test_global_settings_are_validated(client: TestClient) -> None:
    assert client.get("/api/simulation-settings").json()["values"]["llm_runs"] == 20
    assert client.put("/api/simulation-settings", json={"llm_runs": 0}).status_code == 422
    assert client.put("/api/simulation-settings", json={"unknown": 1}).status_code == 422
    r = client.put("/api/simulation-settings", json={"llm_runs": 3})
    assert r.json()["values"]["llm_runs"] == 3
    assert r.json()["defaults"]["llm_runs"] == 20


def test_agent_calls_simulator_with_tool_use(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    sent: list[dict[str, Any]] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        sent.append(body)
        if len(sent) == 1:
            return json_response(200, _tool_use("omikuji", {}))
        return json_response(200, anthropic_message("吉でございます", body["model"]))

    llm(handler)
    agents = client.get("/api/agents").json()
    agent = next(a for a in agents if a["id"] == "simulator-chat-sonnet")
    bot = client.post(
        "/api/bots",
        json={"name": "執事", "agent_id": agent["id"], "settings": agent["default_settings"]},
    ).json()
    conv = client.post("/api/conversations", json={"bot_id": bot["id"]}).json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "引く"})
    assert r.status_code == 200, r.text
    reply = r.json()[1]
    assert reply["content"] == "吉でございます"

    assert {t["name"] for t in sent[0]["tools"]} == {"omikuji", "dice", "dice_sum", "llm"}
    tool_result = sent[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert json.loads(tool_result["content"])["ok"] is True

    [part, main] = reply["parts"]
    assert part["speaker"] == "simulation"
    assert main == {"speaker": "main", "text": "吉でございます"}
    run = client.get(f"/api/simulation-runs/{part['simulation_run_id']}").json()
    assert run["caller"] == "conversation"
    assert run["conversation_id"] == conv["id"]
    assert run["message_id"] == reply["id"]
    assert run["agent_id"] == "simulator-chat-sonnet"


def test_agent_without_tool_use_has_no_parts(
    client: TestClient, llm: Callable[[Handler], None]
) -> None:
    llm(lambda req: json_response(200, anthropic_message("こんにちは", "claude-sonnet-5-5")))
    agents = client.get("/api/agents").json()
    agent = next(a for a in agents if a["id"] == "simulator-chat-sonnet")
    bot = client.post(
        "/api/bots",
        json={"name": "執事", "agent_id": agent["id"], "settings": agent["default_settings"]},
    ).json()
    conv = client.post("/api/conversations", json={"bot_id": bot["id"]}).json()
    reply = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "x"}).json()[
        1
    ]
    assert reply["parts"] is None
    assert client.get("/api/simulation-runs").json() == []
