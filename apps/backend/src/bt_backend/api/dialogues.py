"""エージェント間対話。会話用エージェントと Agent の対話を、1 ターンずつ進める。"""

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from bt_backend.agents import UnknownAgent, get_agent_info, referenced_templates
from bt_backend.api import conversation_bots
from bt_backend.api.schemas import (
    ConversationCommentIn,
    ConversationCommentOut,
    ConversationSettingsOut,
    DialogueCreate,
    DialogueDetail,
    DialogueMessageOut,
    DialogueOut,
    DialogueSettingsOut,
    DialogueTemplateContentOut,
    DialogueTemplateOut,
    MessageCommentIn,
    MessageCommentOut,
)
from bt_backend.api.templates import latest_template_version
from bt_backend.db import RawSessionDep, SessionDep
from bt_backend.dialogues import advance_dialogue, dialogue_messages, resume_dialogue
from bt_backend.models import (
    Bot,
    BotVersion,
    ConversationBot,
    ConversationBotVersion,
    Dialogue,
    DialogueComment,
    DialogueMessage,
    DialogueMessageComment,
    Template,
    TemplateVersion,
    utcnow,
)
from bt_backend.services import ConversationClosed

router = APIRouter(prefix="/api", tags=["dialogues"])

PREVIEW_CHARS = 80


def _templates(session: Session, d: Dialogue) -> list[DialogueTemplateContentOut]:
    out: list[DialogueTemplateContentOut] = []
    for name, version_id in d.template_version_ids.items():
        version = session.get(TemplateVersion, version_id)
        assert version is not None
        out.append(
            DialogueTemplateContentOut(
                name=name,
                template_id=version.template_id,
                version=version.version,
                content=version.content,
            )
        )
    return out


def _dialogue_out(session: Session, d: Dialogue) -> DialogueOut:
    cbot = session.get(ConversationBot, d.conversation_bot_id)
    cversion = session.get(ConversationBotVersion, d.conversation_bot_version_id)
    bot = session.get(Bot, d.bot_id)
    version = session.get(BotVersion, d.bot_version_id)
    assert cbot and cversion and bot and version and d.id is not None
    messages = dialogue_messages(session, d.id)
    first = next((m.content for m in messages if m.role == "speech"), "")
    return DialogueOut(
        **d.model_dump(),
        conversation_bot_name=cbot.name,
        conversation_bot_version=cversion.version,
        bot_name=bot.name,
        bot_version=version.version,
        templates=[
            DialogueTemplateOut.model_validate(t.model_dump()) for t in _templates(session, d)
        ],
        message_count=len(messages),
        preview=first[:PREVIEW_CHARS],
        last_message_at=messages[-1].created_at if messages else None,
    )


def _message_out(
    m: DialogueMessage, comment: DialogueMessageComment | None = None
) -> DialogueMessageOut:
    out = DialogueMessageOut.model_validate(m, from_attributes=True)
    if comment is not None:
        out.comment = MessageCommentOut.model_validate(comment, from_attributes=True)
    return out


def _get_dialogue(session: Session, dialogue_id: int) -> Dialogue:
    d = session.get(Dialogue, dialogue_id)
    if d is None:
        raise HTTPException(404, "エージェント間対話が見つかりません")
    return d


@router.get("/dialogues")
def list_dialogues(
    session: SessionDep, conversation_bot_id: int | None = None, bot_id: int | None = None
) -> list[DialogueOut]:
    query = select(Dialogue).order_by(col(Dialogue.id).desc())
    if conversation_bot_id is not None:
        query = query.where(Dialogue.conversation_bot_id == conversation_bot_id)
    if bot_id is not None:
        query = query.where(Dialogue.bot_id == bot_id)
    return [_dialogue_out(session, d) for d in session.exec(query)]


@router.post("/dialogues")
def create_dialogue(body: DialogueCreate, session: SessionDep) -> DialogueOut:
    """エージェント間対話を始める。両者とテンプレートを、開始時点の最新バージョンに固定する。"""
    cbot = session.get(ConversationBot, body.conversation_bot_id)
    if cbot is None:
        raise HTTPException(404, "会話用エージェントが見つかりません")
    bot = session.get(Bot, body.bot_id)
    if bot is None:
        raise HTTPException(404, "Agent が見つかりません")
    if cbot.unavailable_reason:
        raise HTTPException(
            409, f"この会話用エージェントは停止しています: {cbot.unavailable_reason}"
        )
    if bot.unavailable_reason:
        raise HTTPException(409, f"この Agent は停止しています: {bot.unavailable_reason}")
    cversion = session.exec(
        select(ConversationBotVersion)
        .where(ConversationBotVersion.bot_id == body.conversation_bot_id)
        .order_by(col(ConversationBotVersion.version).desc())
    ).first()
    version = session.exec(
        select(BotVersion)
        .where(BotVersion.bot_id == body.bot_id)
        .order_by(col(BotVersion.version).desc())
    ).first()
    assert cversion and cversion.id is not None and version and version.id is not None

    template_version_ids: dict[str, int] = {}
    missing: list[str] = []
    for name in referenced_templates(cversion.settings):
        template = session.exec(select(Template).where(Template.name == name)).first()
        if template is None or template.id is None:
            missing.append(name)
            continue
        latest = latest_template_version(session, template.id)
        assert latest.id is not None
        template_version_ids[name] = latest.id
    if missing:
        raise HTTPException(
            409, f"会話用エージェントの設定にあるテンプレートが見つかりません: {', '.join(missing)}"
        )

    d = Dialogue(
        conversation_bot_id=body.conversation_bot_id,
        conversation_bot_version_id=cversion.id,
        bot_id=body.bot_id,
        bot_version_id=version.id,
        template_version_ids=template_version_ids,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return _dialogue_out(session, d)


@router.get("/dialogues/{dialogue_id}")
def get_dialogue(dialogue_id: int, session: SessionDep) -> DialogueDetail:
    d = _get_dialogue(session, dialogue_id)
    messages = dialogue_messages(session, dialogue_id)
    comments = {
        mc.message_id: mc
        for mc in session.exec(
            select(DialogueMessageComment).where(
                col(DialogueMessageComment.message_id).in_([m.id for m in messages])
            )
        )
    }
    dialogue_comments = session.exec(
        select(DialogueComment)
        .where(DialogueComment.dialogue_id == dialogue_id)
        .order_by(col(DialogueComment.id))
    )
    return DialogueDetail(
        **_dialogue_out(session, d).model_dump(),
        messages=[_message_out(m, comments.get(m.id or 0)) for m in messages],
        comments=[
            ConversationCommentOut.model_validate(c, from_attributes=True)
            for c in dialogue_comments
        ],
    )


@router.get("/dialogues/{dialogue_id}/settings")
def get_dialogue_settings(dialogue_id: int, session: SessionDep) -> DialogueSettingsOut:
    """対話が使っている（固定されている）両者のバージョンとテンプレート。"""
    d = _get_dialogue(session, dialogue_id)
    cbot = session.get(ConversationBot, d.conversation_bot_id)
    cversion = session.get(ConversationBotVersion, d.conversation_bot_version_id)
    bot = session.get(Bot, d.bot_id)
    version = session.get(BotVersion, d.bot_version_id)
    assert cbot and cversion and bot and version
    try:
        bot_agent_name = get_agent_info(bot.agent_id).name
    except UnknownAgent:
        bot_agent_name = f"（不明な AgentCore: {bot.agent_id}）"
    return DialogueSettingsOut(
        conversation_bot=ConversationSettingsOut(
            bot_id=cbot.id or 0,
            bot_name=cbot.name,
            agent_id=cbot.agent_id,
            agent_name=conversation_bots.agent_name(cbot.agent_id),
            version=cversion.version,
            note=cversion.note,
            created_at=cversion.created_at,
            settings=cversion.settings,
        ),
        bot=ConversationSettingsOut(
            bot_id=bot.id or 0,
            bot_name=bot.name,
            agent_id=bot.agent_id,
            agent_name=bot_agent_name,
            version=version.version,
            note=version.note,
            created_at=version.created_at,
            settings=version.settings,
        ),
        templates=_templates(session, d),
    )


@router.post("/dialogues/{dialogue_id}/turn")
def post_turn(
    dialogue_id: int, session: SessionDep, raw_session: RawSessionDep
) -> list[DialogueMessageOut]:
    """1 ターン（会話用エージェントの発言と、Agent の応答）進める。"""
    d = _get_dialogue(session, dialogue_id)
    try:
        return [_message_out(m) for m in advance_dialogue(session, raw_session, d)]
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e


@router.post("/dialogues/{dialogue_id}/resume")
def resume(dialogue_id: int, session: SessionDep) -> DialogueOut:
    d = _get_dialogue(session, dialogue_id)
    try:
        return _dialogue_out(session, resume_dialogue(session, d))
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e


def _speech(session: Session, message_id: int) -> DialogueMessage:
    m = session.get(DialogueMessage, message_id)
    if m is None:
        raise HTTPException(404, "発言が見つかりません")
    if m.role != "speech":
        raise HTTPException(400, "評価できるのは発言だけです")
    return m


@router.put("/dialogue-messages/{message_id}/comment")
def put_message_comment(
    message_id: int, body: MessageCommentIn, session: SessionDep
) -> MessageCommentOut:
    """会話用エージェント・Agent のどちらの発言にも、評価とコメントを一つ付けられる。

    付け直すと上書きする。
    """
    _speech(session, message_id)
    comment = session.exec(
        select(DialogueMessageComment).where(DialogueMessageComment.message_id == message_id)
    ).first()
    if comment is None:
        comment = DialogueMessageComment(message_id=message_id, rating=body.rating, text=body.text)
    else:
        comment.rating = body.rating
        comment.text = body.text
        comment.updated_at = utcnow()
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return MessageCommentOut.model_validate(comment, from_attributes=True)


@router.delete("/dialogue-messages/{message_id}/comment")
def delete_message_comment(message_id: int, session: SessionDep) -> None:
    _speech(session, message_id)
    comment = session.exec(
        select(DialogueMessageComment).where(DialogueMessageComment.message_id == message_id)
    ).first()
    if comment is not None:
        session.delete(comment)
        session.commit()


@router.post("/dialogues/{dialogue_id}/comments")
def add_dialogue_comment(
    dialogue_id: int, body: ConversationCommentIn, session: SessionDep
) -> ConversationCommentOut:
    _get_dialogue(session, dialogue_id)
    if body.rating is None and body.text.strip() == "":
        raise HTTPException(400, "評価かコメントのどちらかを入れてください")
    comment = DialogueComment(dialogue_id=dialogue_id, rating=body.rating, text=body.text)
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return ConversationCommentOut.model_validate(comment, from_attributes=True)


@router.delete("/dialogue-comments/{comment_id}")
def delete_dialogue_comment(comment_id: int, session: SessionDep) -> None:
    comment = session.get(DialogueComment, comment_id)
    if comment is None:
        raise HTTPException(404, "コメントが見つかりません")
    session.delete(comment)
    session.commit()
