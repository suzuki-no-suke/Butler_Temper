from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BotCreate(BaseModel):
    name: str = Field(min_length=1)
    provider: str
    models: dict[str, Any]
    settings: dict[str, Any] = {}
    note: str = ""


class VersionCreate(BaseModel):
    settings: dict[str, Any]
    note: str = ""


class VersionOut(BaseModel):
    id: int
    version: int
    settings: dict[str, Any]
    note: str
    created_at: datetime


class BotOut(BaseModel):
    id: int
    name: str
    provider: str
    models: dict[str, Any]
    unavailable_reason: str | None
    created_at: datetime
    latest_version: int | None


class BotDetail(BotOut):
    versions: list[VersionOut]


class ConversationCreate(BaseModel):
    bot_id: int


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)


class MessageOut(BaseModel):
    id: int
    seq: int
    role: str
    content: str
    raw_call_id: int | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    bot_id: int
    bot_name: str
    bot_version: int
    title: str
    status: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class RawCallOut(BaseModel):
    id: int
    conversation_id: int | None
    provider: str
    model: str
    source_hash: str
    exchanges: list[dict[str, Any]]
    error: str | None
    started_at: datetime
    finished_at: datetime | None
