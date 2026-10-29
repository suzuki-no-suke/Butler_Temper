"""通常の DB（BOT 設定・会話）のテーブル。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Bot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    # BOT ごとに固定する。変える場合は新しい BOT を作る
    provider: str
    models: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    # モデルが存在しなくなった等で実行を止めている理由
    unavailable_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class BotVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("bot_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    version: int
    settings: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    # 開始時の BOT 設定のバージョンに固定する
    bot_version_id: int = Field(foreign_key="botversion.id")
    title: str = ""
    # active / stopped（エラーで停止）
    status: str = "active"
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    seq: int
    # user / assistant / error
    role: str
    content: str
    # RAW 用の DB の RawCall.id（DB が別なので外部キーにはしない）
    raw_call_id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
