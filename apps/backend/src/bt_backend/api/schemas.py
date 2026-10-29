from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    models: dict[str, str]
    default_settings: dict[str, Any]


class BotCreate(BaseModel):
    name: str = Field(min_length=1)
    agent_id: str
    settings: dict[str, Any]
    note: str = ""


class BotUpdate(BaseModel):
    name: str = Field(min_length=1)


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
    agent_id: str
    agent_name: str
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
    parts: list[dict[str, Any]] | None
    agent_state: dict[str, Any] | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    bot_id: int
    bot_name: str
    bot_version: int
    title: str
    status: str
    agent_state: dict[str, Any] | None
    resumed_from_id: int | None
    created_at: datetime
    message_count: int
    # 最初の利用者の発言（一覧での見分け用）
    preview: str
    last_message_at: datetime | None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class RawCallOut(BaseModel):
    id: int
    conversation_id: int | None
    agent_id: str
    source_hash: str
    exchanges: list[dict[str, Any]]
    error: str | None
    started_at: datetime
    finished_at: datetime | None
