"""RAW 用の DB のテーブル。通常の DB とは別の metadata を持つ。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel

from bt_backend.models import utcnow


class RawBase(SQLModel, registry=registry()):
    pass


class RawCall(RawBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int | None = Field(default=None, index=True)
    provider: str
    model: str
    # Agents モジュールのソースのハッシュ（data/agent_snapshots/<hash>.zip）
    source_hash: str = Field(index=True)
    # HTTP でやり取りした内容（リクエスト・レスポンスの JSON）。認証ヘッダーは含めない
    exchanges: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class SourceSnapshot(RawBase, table=True):
    hash: str = Field(primary_key=True)
    file_count: int
    created_at: datetime = Field(default_factory=utcnow)
