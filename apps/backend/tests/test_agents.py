import json
from collections.abc import Callable
from typing import Any

import httpx2

from bt_backend.agents import ChatTurn, list_agents, run_turn
from bt_backend.agents.context import split_by_chars
from tests.conftest import Handler, anthropic_message, anthropic_not_found, json_response

KEYS = {"anthropic": "secret-a"}


def _turns(*contents: str) -> list[ChatTurn]:
    return [
        ChatTurn(seq=i, role="user" if i % 2 == 0 else "assistant", content=c)
        for i, c in enumerate(contents)
    ]


def _default(agent_id: str) -> dict[str, Any]:
    return next(a.default_settings for a in list_agents() if a.id == agent_id)


def test_split_by_chars_keeps_latest_and_starts_with_user() -> None:
    turns = _turns("aaaa", "bbbb", "cc", "dd", "e")
    older, recent = split_by_chars(turns, 5)
    # "dd" + "e" で 3 文字。"cc" を足すと 5 文字で収まるが、先頭が利用者の発言になるよう調整
    assert [t.content for t in recent] == ["cc", "dd", "e"]
    assert [t.content for t in older] == ["aaaa", "bbbb"]
    older, recent = split_by_chars(turns, 4)
    assert [t.content for t in recent] == ["e"]
    _, recent = split_by_chars(_turns("x" * 100), 1)
    assert len(recent) == 1


def test_every_agent_has_valid_default_settings() -> None:
    agents = list_agents()
    assert {a.id for a in agents} >= {
        "secret-keeper",
        "claude-simple-fable",
        "claude-simple-opus",
        "claude-simple-sonnet",
        "claude-simple-haiku",
    }
    for agent in agents:
        assert agent.models
        assert agent.description


def test_simple_agent_records_raw_exchange(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(200, anthropic_message("やあ")))
    settings = {**_default("claude-simple-sonnet"), "system_prompt": "執事"}
    outcome = run_turn("claude-simple-sonnet", settings, _turns("こんにちは"), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert outcome.text == "やあ"
    [ex] = outcome.exchanges
    assert ex["label"] == "main"
    assert ex["request"]["model"] == "claude-sonnet-5-5"
    assert ex["request"]["system"] == "執事"
    assert ex["response"]["content"][0]["text"] == "やあ"
    assert "secret-a" not in json.dumps(ex)


def test_invalid_settings_is_an_error() -> None:
    outcome = run_turn("claude-simple-opus", {"unknown": 1}, _turns("x"), {}, KEYS)
    assert outcome.error is not None
    assert outcome.exchanges == []


def test_not_found_marks_model_unavailable(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(404, anthropic_not_found()))
    outcome = run_turn("claude-simple-opus", _default("claude-simple-opus"), _turns("x"), {}, KEYS)
    assert outcome.error is not None
    assert outcome.model_unavailable
    assert outcome.exchanges[0]["status"] == 404


def test_server_error_is_not_retried(llm: Callable[[Handler], None]) -> None:
    llm(lambda req: json_response(500, {"type": "error", "error": {"type": "api_error"}}))
    outcome = run_turn("claude-simple-opus", _default("claude-simple-opus"), _turns("x"), {}, KEYS)
    assert outcome.error is not None
    assert not outcome.model_unavailable
    assert len(outcome.exchanges) == 1


def test_missing_api_key() -> None:
    outcome = run_turn("claude-simple-opus", _default("claude-simple-opus"), _turns("x"), {}, {})
    assert outcome.error is not None
    assert "API キー" in outcome.error


class FakeSecretKeeperApi:
    """二層 Agent の三種類の呼び出し（メイン・サブの判定・メモリ）に答える偽の API。"""

    def __init__(self, judge: str) -> None:
        self.judge = judge
        self.calls: list[str] = []
        self.judge_prompts: list[str] = []

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        content = body["messages"][-1]["content"]
        if body["model"] == "claude-opus-5-5":
            self.calls.append("main")
            return json_response(200, anthropic_message("かしこまりました"))
        if "開示条件" in content:
            self.calls.append("sub")
            self.judge_prompts.append(content)
            return json_response(200, anthropic_message(self.judge, "claude-haiku-5-5"))
        self.calls.append("memory")
        return json_response(200, anthropic_message("要約です", "claude-haiku-5-5"))


def _judge(**results: bool) -> str:
    return json.dumps(
        {
            "results": {
                name: {"disclose": d, "reason": "r", "message": f"{name}の秘密は…" if d else ""}
                for name, d in results.items()
            }
        },
        ensure_ascii=False,
    )


def test_secret_keeper_judges_each_secret(llm: Callable[[Handler], None]) -> None:
    api = FakeSecretKeeperApi("判定: " + _judge(金庫=True, 遺言書=False))
    llm(api)
    settings = _default("secret-keeper")
    assert [s["name"] for s in settings["secrets"]] == ["金庫", "遺言書"]
    outcome = run_turn("secret-keeper", settings, _turns("ありがとう"), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert outcome.text == "かしこまりました"
    assert outcome.parts == [
        {"speaker": "main", "text": "かしこまりました"},
        {"speaker": "sub", "secret": "金庫", "text": "金庫の秘密は…"},
    ]
    assert outcome.state["disclosed"] == ["金庫"]
    assert [e["label"] for e in outcome.exchanges] == ["main", "sub"]
    # サブの判定には両方の秘密が入り、メインには秘密が入らない
    main_req, sub_req = (json.dumps(e["request"], ensure_ascii=False) for e in outcome.exchanges)
    for item in settings["secrets"]:
        assert item["secret"] not in main_req
        assert item["secret"] in sub_req

    # 開示済みの秘密は判定しない。残りの秘密だけを判定する
    api.judge = _judge(遺言書=True)
    api.judge_prompts.clear()
    history = _turns("ありがとう", "かしこまりました", "祖父の話をしよう")
    outcome = run_turn("secret-keeper", settings, history, outcome.state, KEYS)
    assert "金庫" not in api.judge_prompts[0]
    assert "遺言書" in api.judge_prompts[0]
    assert outcome.state["disclosed"] == ["金庫", "遺言書"]

    # すべて開示したら判定しない
    api.calls.clear()
    outcome = run_turn("secret-keeper", settings, history, outcome.state, KEYS)
    assert api.calls == ["main"]


def test_secret_keeper_unreadable_judge_does_not_disclose(llm: Callable[[Handler], None]) -> None:
    llm(FakeSecretKeeperApi("よく分かりません"))
    outcome = run_turn("secret-keeper", _default("secret-keeper"), _turns("x"), {}, KEYS)
    assert outcome.error is None
    assert outcome.parts == [{"speaker": "main", "text": "かしこまりました"}]
    assert outcome.state["disclosed"] == []
    assert "_error" in outcome.state["last_judge"]


def test_secret_keeper_reads_single_secret_settings(llm: Callable[[Handler], None]) -> None:
    """秘密が一つだった頃の設定と状態も読める。"""
    api = FakeSecretKeeperApi(_judge(secret=True))
    llm(api)
    old = {
        "secret": "古い秘密",
        "condition": "古い条件",
        "sub": {"judge_instruction": "開示条件: {condition}\n秘密: {secret}"},
    }
    outcome = run_turn("secret-keeper", old, _turns("x"), {}, KEYS)
    assert outcome.error is None, outcome.error
    assert "古い秘密" in api.judge_prompts[0]
    assert outcome.state["disclosed"] == ["secret"]
    # 古い状態（disclosed: true）は、その一つの秘密を開示済みとして読む
    api.calls.clear()
    run_turn("secret-keeper", old, _turns("x"), {"disclosed": True}, KEYS)
    assert api.calls == ["main"]


def test_secret_names_must_be_unique() -> None:
    settings = _default("secret-keeper")
    settings["secrets"][1]["name"] = settings["secrets"][0]["name"]
    outcome = run_turn("secret-keeper", settings, _turns("x"), {}, KEYS)
    assert outcome.error is not None
    assert "重複" in outcome.error


def test_secret_keeper_summarizes_older_turns(llm: Callable[[Handler], None]) -> None:
    api = FakeSecretKeeperApi(_judge(金庫=False, 遺言書=False))
    llm(api)
    settings = _default("secret-keeper")
    settings["memory"]["recent_chars"] = 10
    history = _turns("a" * 10, "b" * 10, "c" * 5)
    outcome = run_turn("secret-keeper", settings, history, {}, KEYS)
    assert api.calls == ["memory", "main", "sub"]
    assert outcome.state["summary"] == "要約です"
    assert outcome.state["summarized_upto_seq"] == 1
    main_req = outcome.exchanges[1]["request"]
    assert "要約です" in main_req["system"]
    assert main_req["messages"] == [{"role": "user", "content": "ccccc"}]

    # 要約済みの発言は、次のターンで再び要約しない
    api.calls.clear()
    history = [*history, ChatTurn(seq=3, role="assistant", content="d"), ChatTurn(4, "user", "e")]
    run_turn("secret-keeper", settings, history, outcome.state, KEYS)
    assert api.calls == ["main", "sub"]


def test_llm_session_openrouter_and_gemini(llm: Callable[[Handler], None]) -> None:
    from bt_backend.agents.llm import LlmSession

    hosts: list[str] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        hosts.append(req.url.host)
        if "openrouter" in req.url.host:
            message = {"role": "assistant", "content": "ok"}
            choice = {"index": 0, "finish_reason": "stop", "message": message}
            body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m"}
            return json_response(200, {**body, "choices": [choice]})
        parts = [{"text": "gem"}]
        return json_response(200, {"candidates": [{"content": {"role": "model", "parts": parts}}]})

    llm(handler)
    session = LlmSession({"openrouter": "secret-r", "gemini": "secret-g"})
    request = {"model": "m", "messages": [{"role": "user", "content": "x"}], "temperature": 0.1}
    reply = session.openai("main", request, openrouter=True)
    assert reply.choices[0].message.content == "ok"
    assert session.gemini("sub", {"model": "g", "contents": "x"}).text == "gem"
    assert hosts[0] == "openrouter.ai"
    assert [e["label"] for e in session.exchanges] == ["main", "sub"]
    assert session.exchanges[0]["request"]["temperature"] == 0.1
    assert "secret-" not in json.dumps(session.exchanges)


class FakeRelayApi:
    """Jev（TypeSafe）と Anthropic の両方に答える偽の API。"""

    def __init__(self, probabilities: list[float]) -> None:
        # 質問の順（secret_0, secret_1, ...）に返す確率
        self.probabilities = probabilities
        self.calls: list[str] = []

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        if req.url.host == "api.typesafe.ai":
            self.calls.append("judge")
            answers = {
                key: {"type": "noul", "noul": self.probabilities[int(key.split("_")[1])]}
                for key in body["questions"]
            }
            usage = {"input_tokens": 10, "output_tokens": 1}
            return json_response(200, {"model": "jev-1.13.0", "usage": usage, "answers": answers})
        self.calls.append("main")
        return json_response(200, anthropic_message("承知いたしました", body["model"]))


RELAY_KEYS = {"anthropic": "secret-a", "typesafe": "secret-t"}


def test_secret_relay_discloses_to_main(llm: Callable[[Handler], None]) -> None:
    api = FakeRelayApi([0.93, 0.2])
    llm(api)
    settings = _default("secret-relay")
    outcome = run_turn("secret-relay", settings, _turns("ありがとう"), {}, RELAY_KEYS)
    assert outcome.error is None, outcome.error
    assert api.calls == ["judge", "main"]
    assert outcome.state == {
        "last_judge": {
            "金庫": {"probability": 0.93, "disclose": True},
            "遺言書": {"probability": 0.2, "disclose": False},
        },
        "disclosed": ["金庫"],
    }
    judge, main = outcome.exchanges
    assert judge["label"] == "judge"
    assert judge["url"] == "https://api.typesafe.ai/v1/systemone"
    conversation = [{"speaker": "主人", "text": "ありがとう"}]
    assert judge["request"]["state"] == {"conversation": conversation}
    questions = judge["request"]["questions"]
    assert [q["instructions"] for q in questions.values()] == [
        s["condition"] for s in settings["secrets"]
    ]
    assert main["request"]["model"] == "claude-sonnet-5-5"
    assert settings["secrets"][0]["secret"] in main["request"]["system"]
    assert settings["secrets"][1]["secret"] not in main["request"]["system"]
    assert "secret-" not in json.dumps(outcome.exchanges)

    # 開示済みの秘密は判定しない
    api.probabilities = [0.9]
    history = _turns("ありがとう", "承知いたしました", "祖父の話をしよう")
    outcome = run_turn("secret-relay", settings, history, outcome.state, RELAY_KEYS)
    assert (
        list(outcome.exchanges[0]["request"]["questions"].values())[0]["instructions"]
        == (settings["secrets"][1]["condition"])
    )
    assert outcome.state["disclosed"] == ["金庫", "遺言書"]
    system = outcome.exchanges[1]["request"]["system"]
    assert all(s["secret"] in system for s in settings["secrets"])

    # すべて開示したら判定しない
    api.calls.clear()
    run_turn("secret-relay", settings, history, outcome.state, RELAY_KEYS)
    assert api.calls == ["main"]


def test_secret_relay_per_secret_threshold(llm: Callable[[Handler], None]) -> None:
    llm(FakeRelayApi([0.5, 0.5]))
    settings = _default("secret-relay")
    settings["secrets"][1]["threshold"] = 0.4
    outcome = run_turn("secret-relay", settings, _turns("こんにちは"), {}, RELAY_KEYS)
    assert outcome.error is None, outcome.error
    assert outcome.state["disclosed"] == ["遺言書"]


def test_secret_relay_reads_single_secret_settings(llm: Callable[[Handler], None]) -> None:
    llm(FakeRelayApi([0.9]))
    old = {
        "secret": "古い秘密",
        "condition": "古い条件",
        "main": {"secret_instruction": "秘密: {secret}"},
        "judge": {"recent_chars": 100, "criteria_true": "はい", "criteria_false": ""},
    }
    outcome = run_turn("secret-relay", old, _turns("x"), {}, RELAY_KEYS)
    assert outcome.error is None, outcome.error
    question = outcome.exchanges[0]["request"]["questions"]["secret_0"]
    assert question["instructions"] == "古い条件"
    assert question["criteria"]["true"] == "はい"
    assert "秘密: - secret: 古い秘密" in outcome.exchanges[1]["request"]["system"]


def test_secret_relay_requires_typesafe_key() -> None:
    outcome = run_turn("secret-relay", _default("secret-relay"), _turns("x"), {}, KEYS)
    assert outcome.error is not None
    assert "typesafe" in outcome.error
