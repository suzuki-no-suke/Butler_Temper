import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_api import _create_bot


def test_export_writes_one_file_per_bot(client: TestClient, tmp_path: Path) -> None:
    import export_bot_settings

    bot_id = _create_bot(client, system_prompt="v1")
    settings = client.get(f"/api/bots/{bot_id}").json()["versions"][0]["settings"]
    client.post(
        f"/api/bots/{bot_id}/versions",
        json={"settings": {**settings, "system_prompt": "v2"}, "note": "二つ目"},
    )
    written = export_bot_settings.export(tmp_path / "out")
    assert [p.name for p in written] == [f"bot-{bot_id}.json"]
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["name"] == "執事"
    assert doc["agent"]["id"] == "claude-simple-opus"
    assert [v["settings"]["system_prompt"] for v in doc["versions"]] == ["v1", "v2"]
    assert doc["versions"][1]["note"] == "二つ目"
