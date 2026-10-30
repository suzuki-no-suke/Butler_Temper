import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from bt_backend.agents import ChatTurn, Interrupt, list_agents, run_turn
from tests.conftest import Handler, anthropic_message, json_response

AGENT_ID = "himitoku-gachi-261030"
KEYS = {"anthropic": "secret-a", "typesafe": "secret-t"}


def _settings() -> dict[str, Any]:
    return next(a.default_settings for a in list_agents() if a.id == AGENT_ID)


def _history(user_turns: int, last: str = "こんにちは") -> list[ChatTurn]:
    """利用者の発言が user_turns 個ある会話（最後は今回の利用者の発言）。"""
    turns: list[ChatTurn] = []
    for i in range(user_turns - 1):
        turns.append(ChatTurn(seq=2 * i, role="user", content=f"発言{i}"))
        turns.append(ChatTurn(seq=2 * i + 1, role="assistant", content=f"応答{i}"))
    turns.append(ChatTurn(seq=2 * (user_turns - 1), role="user", content=last))
    return turns


class FakeApi:
    """Jev（TypeSafe）と Anthropic の両方に答える偽の API。"""

    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = probabilities
        self.calls: list[str] = []

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        if req.url.host == "api.typesafe.ai":
            self.calls.append("secret")
            answers = {
                key: {"type": "noul", "noul": self.probabilities[int(key.split("_")[1])]}
                for key in body["questions"]
            }
            usage = {"input_tokens": 10, "output_tokens": 1}
            return json_response(200, {"model": "jev-1.13.0", "usage": usage, "answers": answers})
        if body["model"] == "claude-haiku-5-5":
            self.calls.append("memory")
            return json_response(200, anthropic_message("新しい記憶", body["model"]))
        self.calls.append("main")
        return json_response(200, anthropic_message("承知いたしました", body["model"]))


def _exchange(outcome: Any, label: str) -> dict[str, Any]:
    return next(e for e in outcome.exchanges if e["label"] == label)


def test_secret_returns_to_main_as_memory(llm: Callable[[Handler], None]) -> None:
    api = FakeApi([0.93, 0.2])
    llm(api)
    settings = _settings()
    outcome = run_turn(AGENT_ID, settings, _history(1, "ありがとう"), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert api.calls == ["secret", "main"]
    assert outcome.text == "承知いたしました"
    assert outcome.parts == [{"speaker": "main", "text": "承知いたしました"}]
    assert outcome.state["disclosed"] == ["金庫"]
    main = _exchange(outcome, "main")
    assert main["request"]["model"] == "claude-opus-5-5"
    system = main["request"]["system"]
    assert "# 思い出したこと" in system
    assert settings["secrets"][0]["secret"] in system
    assert settings["secrets"][1]["secret"] not in system
    assert "# 応答の長さ" in system
    assert _exchange(outcome, "secret")["request"]["state"] == {
        "conversation": [{"speaker": "主人", "text": "ありがとう"}]
    }
    assert "secret-" not in json.dumps(outcome.exchanges)


def test_main_context_is_recent_chars(llm: Callable[[Handler], None]) -> None:
    llm(FakeApi([0.0, 0.0]))
    settings = _settings()
    history = [
        ChatTurn(seq=0, role="user", content="古" * 3000),
        ChatTurn(seq=1, role="assistant", content="はい"),
        ChatTurn(seq=2, role="user", content="今"),
    ]
    outcome = run_turn(AGENT_ID, settings, history, {}, KEYS)
    assert outcome.error is None, outcome.error
    assert _exchange(outcome, "main")["request"]["messages"] == [{"role": "user", "content": "今"}]


def test_memory_is_updated_every_five_turns(llm: Callable[[Handler], None]) -> None:
    api = FakeApi([0.0, 0.0])
    llm(api)
    settings = _settings()
    outcome = run_turn(AGENT_ID, settings, _history(4), {}, KEYS)
    assert "memory" not in api.calls
    assert outcome.state["memory"] == {}

    api.calls.clear()
    outcome = run_turn(AGENT_ID, settings, _history(5), {"disclosed": ["金庫"]}, KEYS)
    assert outcome.error is None, outcome.error
    assert api.calls == ["secret", "main", "memory"]
    assert outcome.state["memory"] == {
        "summary": "新しい記憶",
        "summarized_upto_seq": 9,
        "updated_at_turn": 5,
    }
    memory = _exchange(outcome, "memory")["request"]
    assert "1000 文字以内" in memory["system"]
    content = memory["messages"][0]["content"]
    # 今回のメインの応答と、開示済みの秘匿情報も要約に含める
    assert "執事: 承知いたしました" in content
    assert settings["secrets"][0]["secret"] in content

    # 次のターンからは、記憶がメインと秘匿管理に渡る
    outcome = run_turn(AGENT_ID, settings, _history(6), outcome.state, KEYS)
    assert "# これまでの記憶\n新しい記憶" in _exchange(outcome, "main")["request"]["system"]
    assert _exchange(outcome, "secret")["request"]["state"]["memory"] == "新しい記憶"


def test_system_notices_go_to_selected_targets(llm: Callable[[Handler], None]) -> None:
    llm(FakeApi([0.0, 0.0]))
    settings = _settings()

    # 10 往復ごとの通知は秘匿管理だけ
    outcome = run_turn(AGENT_ID, settings, _history(10), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert _exchange(outcome, "secret")["request"]["state"]["system_notices"] == [
        "会話が 10 往復に達しました。"
    ]
    assert "システムからの通知" not in _exchange(outcome, "main")["request"]["system"]
    assert outcome.parts == [{"speaker": "main", "text": "承知いたしました"}]

    # 100 往復を越えたら全体に通知する
    outcome = run_turn(AGENT_ID, settings, _history(101), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert outcome.parts is not None
    assert outcome.parts[0]["speaker"] == "system"
    assert "101 往復" in outcome.parts[0]["text"]
    assert "101 往復" in _exchange(outcome, "main")["request"]["system"]
    assert "101 往復" in _exchange(outcome, "secret")["request"]["state"]["system_notices"][0]


def test_interrupts_go_to_selected_targets(llm: Callable[[Handler], None]) -> None:
    llm(FakeApi([0.0, 0.0]))
    interrupts = [
        Interrupt(id=1, message="窓だけ", targets=["window"]),
        Interrupt(id=2, message="メインと秘匿管理", targets=["main", "secret"]),
    ]
    outcome = run_turn(AGENT_ID, _settings(), _history(1), {}, KEYS, interrupts)
    assert outcome.error is None, outcome.error
    assert outcome.parts == [
        {"speaker": "system", "text": "窓だけ"},
        {"speaker": "main", "text": "承知いたしました"},
    ]
    system = _exchange(outcome, "main")["request"]["system"]
    assert "メインと秘匿管理" in system and "窓だけ" not in system
    assert _exchange(outcome, "secret")["request"]["state"]["system_notices"] == [
        "メインと秘匿管理"
    ]
    assert outcome.state["system"]["delivered_interrupts"] == [1, 2]


def test_error_pauses_conversation(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(500, {"type": "error", "error": {"type": "api_error"}}))
    outcome = run_turn(AGENT_ID, _settings(), _history(1), {}, KEYS)
    assert outcome.error is not None
    assert outcome.error.startswith("システム: エラーが起きたため、会話を一時停止しました")
    assert not outcome.model_unavailable


def test_rule_needs_one_condition() -> None:
    from bt_backend.agents import InvalidSettings, validate_settings

    settings = _settings()
    settings["system"]["rules"] = [{"name": "x", "targets": ["main"], "message": "m"}]
    try:
        validate_settings(AGENT_ID, settings)
    except InvalidSettings:
        return
    raise AssertionError("every も over も無い規則が通った")


def test_interrupt_api(
    client: TestClient, llm: Callable[[Handler], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    llm(FakeApi([0.0, 0.0]))
    from bt_backend import services

    monkeypatch.setattr(services, "api_keys", lambda: KEYS)
    bot = client.post(
        "/api/bots", json={"name": "ガチ", "agent_id": AGENT_ID, "settings": _settings()}
    ).json()
    conv = client.post("/api/conversations", json={"bot_id": bot["id"]}).json()
    url = f"/api/conversations/{conv['id']}/interrupts"

    assert client.post(url, json={"message": "x", "targets": ["nobody"]}).status_code == 422
    r = client.post(url, json={"message": "まもなく終了します", "targets": ["window", "main"]})
    assert r.status_code == 200, r.text
    assert r.json()["delivered_message_id"] is None

    [_, reply] = client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "やあ"}
    ).json()
    assert reply["role"] == "assistant", reply
    assert reply["parts"][0] == {"speaker": "system", "text": "まもなく終了します"}
    [interrupt] = client.get(url).json()
    assert interrupt["delivered_message_id"] == reply["id"]

    # 伝えた割込みは次のターンには渡さない
    [_, reply] = client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "続き"}
    ).json()
    assert reply["parts"] == [{"speaker": "main", "text": "承知いたしました"}]


def test_interrupt_api_refuses_agents_without_interrupts(client: TestClient) -> None:
    bots = client.get("/api/bots").json()
    if not bots:
        agent = next(a for a in list_agents() if a.id == "claude-simple-haiku")
        bots = [
            client.post(
                "/api/bots",
                json={"name": "s", "agent_id": agent.id, "settings": agent.default_settings},
            ).json()
        ]
    simple = next(b for b in bots if b["agent_id"].startswith("claude-simple"))
    conv = client.post("/api/conversations", json={"bot_id": simple["id"]}).json()
    r = client.post(
        f"/api/conversations/{conv['id']}/interrupts", json={"message": "x", "targets": ["main"]}
    )
    assert r.status_code == 409
