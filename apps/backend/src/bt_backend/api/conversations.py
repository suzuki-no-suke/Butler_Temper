from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from bt_backend.agents import UnknownAgent, get_agent_info
from bt_backend.api.schemas import (
    ConversationCommentOut,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationSettingsOut,
    InterruptCreate,
    InterruptOut,
    MessageCommentOut,
    MessageCreate,
    MessageOut,
    RawCallOut,
)
from bt_backend.db import RawSessionDep, SessionDep
from bt_backend.models import (
    Bot,
    BotVersion,
    Conversation,
    ConversationComment,
    ConversationInterrupt,
    Message,
    MessageComment,
    ParallelCandidate,
    ParallelRound,
)
from bt_backend.raw_models import RawCall
from bt_backend.services import (
    ConversationClosed,
    messages_of,
    resume_conversation,
    send_message,
)

router = APIRouter(prefix="/api", tags=["conversations"])


PREVIEW_CHARS = 80


def _conversation_out(session: Session, c: Conversation) -> ConversationOut:
    bot = session.get(Bot, c.bot_id)
    version = session.get(BotVersion, c.bot_version_id)
    assert bot is not None and version is not None and c.id is not None
    messages = messages_of(session, c.id)
    first_user = next((m.content for m in messages if m.role == "user"), "")
    parallel_id = None
    if c.parallel_candidate_id is not None:
        candidate = session.get(ParallelCandidate, c.parallel_candidate_id)
        assert candidate is not None
        round_ = session.get(ParallelRound, candidate.round_id)
        assert round_ is not None
        parallel_id = round_.parallel_conversation_id
    return ConversationOut(
        **c.model_dump(),
        parallel_conversation_id=parallel_id,
        bot_name=bot.name,
        bot_version=version.version,
        message_count=len(messages),
        preview=first_user[:PREVIEW_CHARS],
        last_message_at=messages[-1].created_at if messages else None,
    )


def _message_out(m: Message, comment: MessageComment | None = None) -> MessageOut:
    out = MessageOut.model_validate(m, from_attributes=True)
    if comment is not None:
        out.comment = MessageCommentOut.model_validate(comment, from_attributes=True)
    return out


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
        raise HTTPException(404, "Agent が見つかりません")
    if bot.unavailable_reason:
        raise HTTPException(409, f"この Agent は停止しています: {bot.unavailable_reason}")
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


@router.post("/conversations/{conversation_id}/resume")
def resume(conversation_id: int, session: SessionDep) -> ConversationOut:
    """会話を続ける。止まっていない会話はそのまま、エラーで止まった会話は引き継いだ新しい会話を返す。"""
    c = _get_conversation(session, conversation_id)
    try:
        return _conversation_out(session, resume_conversation(session, c))
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, session: SessionDep) -> ConversationDetail:
    c = _get_conversation(session, conversation_id)
    messages = messages_of(session, conversation_id)
    comments = {
        mc.message_id: mc
        for mc in session.exec(
            select(MessageComment).where(
                col(MessageComment.message_id).in_([m.id for m in messages])
            )
        )
    }
    conversation_comments = session.exec(
        select(ConversationComment)
        .where(ConversationComment.conversation_id == conversation_id)
        .order_by(col(ConversationComment.id))
    )
    return ConversationDetail(
        **_conversation_out(session, c).model_dump(),
        messages=[_message_out(m, comments.get(m.id or 0)) for m in messages],
        comments=[
            ConversationCommentOut.model_validate(cc, from_attributes=True)
            for cc in conversation_comments
        ],
    )


@router.get("/conversations/{conversation_id}/settings")
def get_conversation_settings(conversation_id: int, session: SessionDep) -> ConversationSettingsOut:
    """会話が使っている（固定されている）Agent のバージョン。"""
    c = _get_conversation(session, conversation_id)
    bot = session.get(Bot, c.bot_id)
    version = session.get(BotVersion, c.bot_version_id)
    assert bot is not None and version is not None
    try:
        agent_name = get_agent_info(bot.agent_id).name
    except UnknownAgent:
        agent_name = f"（不明な AgentCore: {bot.agent_id}）"
    return ConversationSettingsOut(
        bot_id=bot.id or 0,
        bot_name=bot.name,
        agent_id=bot.agent_id,
        agent_name=agent_name,
        version=version.version,
        note=version.note,
        created_at=version.created_at,
        settings=version.settings,
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


@router.post("/conversations/{conversation_id}/interrupts")
def create_interrupt(
    conversation_id: int, body: InterruptCreate, session: SessionDep
) -> InterruptOut:
    """割込み要求を入れる。次のターンに、targets に挙げた相手へ伝わる。"""
    c = _get_conversation(session, conversation_id)
    if c.status != "active":
        raise HTTPException(409, "この会話はエラーで停止しています")
    bot = session.get(Bot, c.bot_id)
    assert bot is not None
    try:
        accepted = get_agent_info(bot.agent_id).interrupt_targets
    except UnknownAgent as e:
        raise HTTPException(409, f"AgentCore が見つかりません: {bot.agent_id}") from e
    if not accepted:
        raise HTTPException(409, "この Agent の AgentCore は割込みを受け付けません")
    unknown = [t for t in body.targets if t not in accepted]
    if unknown:
        raise HTTPException(
            422, f"伝えられない相手です: {', '.join(unknown)}（使える相手: {', '.join(accepted)}）"
        )
    interrupt = ConversationInterrupt(
        conversation_id=conversation_id, message=body.message, targets=list(body.targets)
    )
    session.add(interrupt)
    session.commit()
    session.refresh(interrupt)
    return InterruptOut.model_validate(interrupt, from_attributes=True)


@router.get("/conversations/{conversation_id}/interrupts")
def list_interrupts(conversation_id: int, session: SessionDep) -> list[InterruptOut]:
    _get_conversation(session, conversation_id)
    return [
        InterruptOut.model_validate(i, from_attributes=True)
        for i in session.exec(
            select(ConversationInterrupt)
            .where(ConversationInterrupt.conversation_id == conversation_id)
            .order_by(col(ConversationInterrupt.id))
        )
    ]


@router.get("/raw-calls/{raw_call_id}")
def get_raw_call(raw_call_id: int, raw_session: RawSessionDep) -> RawCallOut:
    raw = raw_session.get(RawCall, raw_call_id)
    if raw is None:
        raise HTTPException(404, "RAW 記録が見つかりません")
    return RawCallOut.model_validate(raw, from_attributes=True)
