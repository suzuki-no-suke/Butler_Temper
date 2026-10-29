from pathlib import Path

from bt_backend.snapshot import collect_files, compute_hash, save_snapshot


def _make_tree(root: Path) -> Path:
    agents = root / "src" / "agents"
    (agents / "providers").mkdir(parents=True)
    (agents / "__init__.py").write_text("a = 1\n")
    (agents / "providers" / "x.py").write_text("b = 2\n")
    (agents / "__pycache__").mkdir()
    (agents / "__pycache__" / "x.cpython.pyc").write_bytes(b"\0")
    (root / "pyproject.toml").write_text("[project]\n")
    (root / "uv.lock").write_text("lock\n")
    return agents


def test_collects_agents_and_lock_files(tmp_path: Path) -> None:
    agents = _make_tree(tmp_path)
    files = collect_files(agents, tmp_path)
    assert sorted(files) == [
        "agents/__init__.py",
        "agents/providers/x.py",
        "pyproject.toml",
        "uv.lock",
    ]


def test_hash_depends_on_content_only(tmp_path: Path) -> None:
    agents = _make_tree(tmp_path)
    first = compute_hash(collect_files(agents, tmp_path))
    (agents / "__init__.py").touch()
    assert compute_hash(collect_files(agents, tmp_path)) == first
    (tmp_path / "uv.lock").write_text("lock2\n")
    assert compute_hash(collect_files(agents, tmp_path)) != first


def test_save_snapshot_once(tmp_path: Path) -> None:
    agents = _make_tree(tmp_path)
    files = collect_files(agents, tmp_path)
    h = compute_hash(files)
    out = tmp_path / "snap"
    target = save_snapshot(files, h, out)
    assert target.name == f"{h}.zip"
    mtime = target.stat().st_mtime_ns
    save_snapshot(files, h, out)
    assert target.stat().st_mtime_ns == mtime
