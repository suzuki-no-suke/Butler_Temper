import json
import random
import re
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from tests.conftest import Handler, anthropic_message, json_response

AGENT_ID = "kamidanomi-wanda"


@pytest.fixture(autouse=True)
def fixed_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    from bt_backend.agents import kamidanomi
    from bt_backend.simulators import chance

    monkeypatch.setattr(chance, "rng", random.Random(1))
    monkeypatch.setattr(kamidanomi, "rng", random.Random(1))


def _tool_use(name: str, args: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        **anthropic_message("", model),
        "content": [{"type": "tool_use", "id": "tu_1", "name": name, "input": args}],
        "stop_reason": "tool_use",
    }


class Shop:
    """丁稚とワンダの応答を、テストごとに決める。送られた内容を残す。"""

    def __init__(self) -> None:
        self.report: dict[str, Any] = {}
        # ワンダの応答。None ならシステムプロンプトに合言葉があればそれを言う
        self.main: list[dict[str, Any]] = []
        self.detchi_sent: list[dict[str, Any]] = []
        self.main_sent: list[dict[str, Any]] = []

    def handler(self, req: httpx2.Request) -> httpx2.Response:
        body = json.loads(req.content)
        model = body["model"]
        if any(t["name"] == "report" for t in body.get("tools", [])):
            self.detchi_sent.append(body)
            report = {"stage": "icebreak", "ready": False, "ending": False, "disclose": []}
            return json_response(200, _tool_use("report", {**report, **self.report}, model))
        self.main_sent.append(body)
        if self.main:
            return json_response(200, self.main.pop(0))
        words = re.search(r"つづきの合言葉「(.+?)」", body["system"])
        text = f"合言葉は {words.group(1)} でぃ" if words else "へい、いらっしゃい"
        return json_response(200, anthropic_message(text, model))


@pytest.fixture
def shop(llm: Callable[[Handler], None]) -> Shop:
    s = Shop()
    llm(s.handler)
    return s


def _bot(client: TestClient) -> int:
    agent = next(a for a in client.get("/api/agents").json() if a["id"] == AGENT_ID)
    bot = client.post(
        "/api/bots",
        json={"name": "ワンダ", "agent_id": AGENT_ID, "settings": agent["default_settings"]},
    ).json()
    return int(bot["id"])


def _conversation(client: TestClient, bot_id: int) -> int:
    return int(client.post("/api/conversations", json={"bot_id": bot_id}).json()["id"])


def _say(client: TestClient, conv_id: int, text: str) -> dict[str, Any]:
    r = client.post(f"/api/conversations/{conv_id}/messages", json={"content": text})
    assert r.status_code == 200, r.text
    reply: dict[str, Any] = r.json()[1]
    assert reply["role"] == "assistant", reply
    return reply


def _state(client: TestClient, conv_id: int) -> dict[str, Any]:
    state: dict[str, Any] = client.get(f"/api/conversations/{conv_id}").json()["messages"][-1][
        "agent_state"
    ]
    return state


def test_print_adds_hint_and_key_only_on_first_receipt(client: TestClient, shop: Shop) -> None:
    bot_id = _bot(client)
    conv = _conversation(client, bot_id)
    omikuji = {"kind": "おみくじ模倣", "fields": {"願いごと": "健康", "ひとこと": "よく寝なせぇ"}}
    shop.main = [
        _tool_use("print_receipt", omikuji, "claude-sonnet-5-5"),
        anthropic_message("ほらよ", "claude-sonnet-5-5"),
        _tool_use("print_receipt", omikuji, "claude-sonnet-5-5"),
        anthropic_message("もう一枚", "claude-sonnet-5-5"),
    ]
    reply = _say(client, conv, "おみくじ引きたい")
    assert reply["content"] == "ほらよ"
    [printed, main] = reply["parts"]
    assert printed["speaker"] == "simulation"
    assert main == {"speaker": "main", "text": "ほらよ"}
    run = client.get(f"/api/simulation-runs/{printed['simulation_run_id']}").json()
    assert run["simulator"] == "receipt"
    text = run["result"]["printed"]
    assert "店主さんの名前はわかりましたか？" in text
    assert "スクラップヤードにようこそ" in text
    assert "| 願いごと | 健康 |" in text
    assert run["result"]["fortune"] in text

    # ワンダには末尾の印字（ヒント・カギ）を返さない
    tool_result = shop.main_sent[1]["messages"][-1]["content"][0]
    back = json.loads(tool_result["content"])
    assert back["ok"] is True
    assert back["fortune"] == run["result"]["fortune"]
    assert "スクラップヤード" not in tool_result["content"]

    reply = _say(client, conv, "もう一枚")
    second = client.get(f"/api/simulation-runs/{reply['parts'][0]['simulation_run_id']}").json()
    assert "スクラップヤードにようこそ" not in second["result"]["printed"]
    assert "店主さんの名前はわかりましたか？" in second["result"]["printed"]
    assert "# このお客さんに渡したもの" in shop.main_sent[2]["system"]


def test_print_is_refused_until_fields_are_filled(client: TestClient, shop: Shop) -> None:
    conv = _conversation(client, _bot(client))
    shop.main = [
        _tool_use("print_receipt", {"kind": "おみくじ模倣", "fields": {}}, "claude-sonnet-5-5"),
        anthropic_message("願いごとは？", "claude-sonnet-5-5"),
    ]
    reply = _say(client, conv, "おみくじ")
    tool_result = shop.main_sent[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert json.loads(tool_result["content"])["missing"] == ["願いごと", "ひとこと"]
    assert [p["speaker"] for p in reply["parts"]] == ["main"]
    assert client.get("/api/simulation-runs").json() == []


def test_receipt_items_total_is_computed(client: TestClient, shop: Shop) -> None:
    conv = _conversation(client, _bot(client))
    items = [{"name": "大根", "price": 120}, {"name": "豆腐", "price": 80}]
    shop.main = [
        _tool_use("print_receipt", {"kind": "レシート模倣", "items": items}, "claude-sonnet-5-5"),
        anthropic_message("合計二百文でい", "claude-sonnet-5-5"),
    ]
    reply = _say(client, conv, "レシートちょうだい")
    run = client.get(f"/api/simulation-runs/{reply['parts'][0]['simulation_run_id']}").json()
    assert run["result"]["total"] == 200
    assert "| 合計 | 200円 |" in run["result"]["printed"]


def test_passphrase_carries_visits_and_disclosed_secrets(client: TestClient, shop: Shop) -> None:
    bot_id = _bot(client)
    first = _conversation(client, bot_id)
    shop.report = {"disclose": ["名前"]}
    _say(client, first, "お名前は？")
    assert "あなたの名前はワンダ" in shop.main_sent[-1]["system"]

    shop.report = {"ending": True, "stage": "closing"}
    reply = _say(client, first, "またね")
    state = _state(client, first)
    words = state["passphrase"]
    assert state["ended"] is True
    assert all(w in reply["content"] for w in words)

    # 会話の終わりは一度きり
    _say(client, first, "やっぱりもう少し")
    assert "つづきの合言葉" not in shop.main_sent[-1]["system"]

    # 次の会話で合言葉を言う（順番が違ってもよい）
    second = _conversation(client, bot_id)
    shop.report = {"passphrase": list(reversed(words))}
    _say(client, second, "　".join(reversed(words)))
    system = shop.main_sent[-1]["system"]
    assert "ワンダって名前までお話ししたお客さんだね" in system
    assert "あなたの名前はワンダ" in system
    state = _state(client, second)
    assert state["visits"] == 1
    assert state["disclosed"] == ["名前"]
    # 照合済みの会話で別の合言葉が出たら、たしなめて無視する
    shop.report = {"passphrase": ["りんご", "みかん", "ぶどう"]}
    _say(client, second, "りんご みかん ぶどう")
    assert "合言葉二つですかい" in shop.main_sent[-1]["system"]
    assert _state(client, second)["visits"] == 1

    # 2 回目の来店では、2 つ目のヒントを印刷する
    shop.report = {}
    shop.main = [
        _tool_use(
            "print_receipt",
            {"kind": "おみくじ模倣", "fields": {"願いごと": "金運", "ひとこと": "倹約"}},
            "claude-sonnet-5-5",
        ),
        anthropic_message("ほらよ", "claude-sonnet-5-5"),
    ]
    reply = _say(client, second, "おみくじ")
    run = client.get(f"/api/simulation-runs/{reply['parts'][0]['simulation_run_id']}").json()
    assert "店主さんの見た目って気になりませんか？" in run["result"]["printed"]


def test_unknown_passphrase_pretends_and_discloses_name(client: TestClient, shop: Shop) -> None:
    conv = _conversation(client, _bot(client))
    shop.report = {"passphrase": ["なべ", "はくさい", "とうふ"]}
    _say(client, conv, "なべ はくさい とうふ")
    system = shop.main_sent[-1]["system"]
    assert "ワンダって名前までお話ししたお客さんだね" in system
    state = _state(client, conv)
    assert state["visits"] == 0
    assert state["disclosed"] == ["名前"]


def test_secret_word_is_printed_and_hidden_from_wanda(client: TestClient, shop: Shop) -> None:
    conv = _conversation(client, _bot(client))
    shop.report = {"disclose": ["秘密の合言葉"]}
    reply = _say(client, conv, "スクラップヤードにようこそ")
    [printed, _] = reply["parts"]
    run = client.get(f"/api/simulation-runs/{printed['simulation_run_id']}").json()
    assert "NT名古屋は楽しいですね" in run["result"]["printed"]
    system = shop.main_sent[-1]["system"]
    assert "NT名古屋" not in system
    assert "オーナーにお伝えくだせぇ" in system
    assert "スクラップヤードにようこそ" in shop.detchi_sent[-1]["messages"][0]["content"]
