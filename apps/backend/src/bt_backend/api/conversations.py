from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from bt_backend.api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    MessageCreate,
    MessageOut,
    RawCallOut,
)
from bt_backend.db import RawSessionDep, SessionDep
from bt_backend.models import Bot, BotVersion, Conversation, Message
from bt_backend.raw_models import RawCall
from bt_backend.services import ConversationClosed, messages_of, send_message

router = APIRouter(prefix="/api", tags=["conversations"])


def _conversation_out(session: Session, c: Conversation) -> ConversationOut:
    bot = session.get(Bot, c.bot_id)
    version = session.get(BotVersion, c.bot_version_id)
    assert bot is not None and version is not None
    return ConversationOut(**c.model_dump(), bot_name=bot.name, bot_version=version.version)


def _message_out(m: Message) -> MessageOut:
    return MessageOut.model_validate(m, from_attributes=True)


def _get_conversation(session: Session, conversation_id: int) -> Conversation:
    c = session.get(Conversation, conversation_id)
    if c is None:
        raise HTTPException(404, "会話が見つかりません")
    return c


@router.get("/conversations")
def list_conversations(session: SessionDep, bot_id: int | None = None) -> list[ConversationOut]:
    query = select(Conversation).order_by(col(Conversation.id).desc())
    if bot_id is not None:
        query = query.where(Conversation.bot_id == bot_id)
    return [_conversation_out(session, c) for c in session.exec(query)]


@router.post("/conversations")
def create_conversation(body: ConversationCreate, session: SessionDep) -> ConversationOut:
    bot = session.get(Bot, body.bot_id)
    if bot is None:
        raise HTTPException(404, "BOT が見つかりません")
    if bot.unavailable_reason:
        raise HTTPException(409, f"この BOT は停止しています: {bot.unavailable_reason}")
    # 開始時点の最新バージョンに固定する
    version = session.exec(
        select(BotVersion)
        .where(BotVersion.bot_id == body.bot_id)
        .order_by(col(BotVersion.version).desc())
    ).first()
    assert version is not None and version.id is not None
    c = Conversation(bot_id=body.bot_id, bot_version_id=version.id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return _conversation_out(session, c)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, session: SessionDep) -> ConversationDetail:
    c = _get_conversation(session, conversation_id)
    return ConversationDetail(
        **_conversation_out(session, c).model_dump(),
        messages=[_message_out(m) for m in messages_of(session, conversation_id)],
    )


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: int,
    body: MessageCreate,
    session: SessionDep,
    raw_session: RawSessionDep,
) -> list[MessageOut]:
    c = _get_conversation(session, conversation_id)
    try:
        return [_message_out(m) for m in send_message(session, raw_session, c, body.content)]
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e


@router.get("/raw-calls/{raw_call_id}")
def get_raw_call(raw_call_id: int, raw_session: RawSessionDep) -> RawCallOut:
    raw = raw_session.get(RawCall, raw_call_id)
    if raw is None:
        raise HTTPException(404, "RAW 記録が見つかりません")
    return RawCallOut.model_validate(raw, from_attributes=True)
