from pathlib import Path

import pytest

from bt_backend.config import Settings


def test_bt_prefixed_key_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "plain")
    monkeypatch.setenv("BT_ANTHROPIC_API_KEY", "prefixed")
    assert Settings(_env_file=tmp_path / "none.env").anthropic_api_key == "prefixed"


def test_plain_key_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BT_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "plain")
    assert Settings(_env_file=tmp_path / "none.env").anthropic_api_key == "plain"
