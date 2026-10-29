"""Agents モジュールのソースのバックアップ。

Agents フォルダ全体と pyproject.toml / uv.lock を、ファイルのパスと中身から計算した
ハッシュをファイル名にして data/agent_snapshots/<hash>.zip に保存する。
"""

import hashlib
import zipfile
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session

from bt_backend.config import BACKEND_ROOT, get_settings
from bt_backend.db import get_raw_engine
from bt_backend.raw_models import SourceSnapshot

AGENTS_DIR = Path(__file__).resolve().parent / "agents"
EXTRA_FILES = ("pyproject.toml", "uv.lock")
_EXCLUDED_DIRS = {"__pycache__"}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def collect_files(agents_dir: Path = AGENTS_DIR, root: Path = BACKEND_ROOT) -> dict[str, Path]:
    """zip 内のパス -> 実ファイル。"""
    files: dict[str, Path] = {}
    for path in agents_dir.rglob("*"):
        if not path.is_file() or path.suffix in _EXCLUDED_SUFFIXES:
            continue
        if _EXCLUDED_DIRS & set(path.relative_to(agents_dir).parts):
            continue
        files["agents/" + path.relative_to(agents_dir).as_posix()] = path
    for name in EXTRA_FILES:
        if (root / name).is_file():
            files[name] = root / name
    return files


def compute_hash(files: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files):
        content = files[name].read_bytes()
        digest.update(name.encode() + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def save_snapshot(files: dict[str, Path], source_hash: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{source_hash}.zip"
    if target.exists():
        return target
    tmp = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            zf.write(files[name], name)
    tmp.replace(target)
    return target


@lru_cache
def current_source_hash() -> str:
    """起動中のプロセスで使っているソースのハッシュ。初回呼び出し時に保存も行う。"""
    files = collect_files()
    source_hash = compute_hash(files)
    save_snapshot(files, source_hash, get_settings().snapshot_dir)
    with Session(get_raw_engine()) as session:
        if session.get(SourceSnapshot, source_hash) is None:
            session.add(SourceSnapshot(hash=source_hash, file_count=len(files)))
            session.commit()
    return source_hash
