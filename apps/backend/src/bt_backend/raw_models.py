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
    # エージェント間対話の記録なら、その Dialogue.id（conversation_id は None）
    dialogue_id: int | None = Field(default=None, index=True)
    # 並行会話の候補の記録なら、その ParallelCandidate.id（conversation_id は None）
    parallel_candidate_id: int | None = Field(default=None, index=True)
    agent_id: str = Field(sa_column_kwargs={"server_default": ""})
    # Agents モジュールのソースのハッシュ（data/agent_snapshots/<hash>.zip）
    source_hash: str = Field(index=True)
    # HTTP でやり取りした内容（リクエスト・レスポンスの JSON）。認証ヘッダーは含めない
    # 各要素の label は、Agent 内での呼び出しの役割（main / sub / memory など）
    exchanges: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class SourceSnapshot(RawBase, table=True):
    hash: str = Field(primary_key=True)
    file_count: int
    created_at: datetime = Field(default_factory=utcnow)


class SimulationRawCall(RawBase, table=True):
    """シミュレート用の RAW。

    シミュレータ内の LLM 呼び出しを 1 回分ずつ、シミュレータごとに分けて置く。
    """

    id: int | None = Field(default=None, primary_key=True)
    simulator: str = Field(index=True)
    # 通常の DB の SimulationRun.id
    simulation_run_id: int = Field(index=True)
    # シミュレータ内での呼び出しの役割（run-1 / merge など）
    label: str
    exchanges: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
