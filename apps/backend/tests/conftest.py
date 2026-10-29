import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from alembic import command
from fastapi.testclient import TestClient

MIGRATE_DIR = Path(__file__).resolve().parents[2] / "migrate"
TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
sys.path.insert(0, str(MIGRATE_DIR))
sys.path.insert(0, str(TOOLS_DIR))

Handler = Callable[[httpx2.Request], httpx2.Response]


def _clear_caches() -> None:
    from bt_backend import config, db, snapshot

    config.get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_raw_engine.cache_clear()
    snapshot.current_source_hash.cache_clear()


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("BT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BT_ENV_FILE", str(tmp_path / "none.env"))
    for key in ("BT_DATABASE_URL", "BT_RAW_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    # 実行環境にある本物のキーを使わない
    for name in ("ANTHROPIC", "OPENAI", "GEMINI", "OPENROUTER", "TYPESAFE"):
        monkeypatch.delenv(f"BT_{name}_API_KEY", raising=False)
        monkeypatch.delenv(f"{name}_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _clear_caches()
    import migrate

    for target in migrate.TARGETS:
        command.upgrade(migrate.config_for(target), "head")
    yield tmp_path / "data"
    _clear_caches()


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    from bt_backend.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    """Agent が使う HTTP 通信を差し替える。"""
    from bt_backend.agents import llm as llm_module

    def install(handler: Handler) -> None:
        monkeypatch.setattr(llm_module, "transport_override", httpx2.MockTransport(handler))

    return install


def json_response(status: int, body: dict[str, Any]) -> httpx2.Response:
    return httpx2.Response(
        status, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )


def anthropic_message(text: str, model: str = "claude-opus-5-5") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def anthropic_not_found() -> dict[str, Any]:
    return {"type": "error", "error": {"type": "not_found_error", "message": "model: x"}}
