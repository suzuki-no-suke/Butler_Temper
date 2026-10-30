"""会話用エージェントの管理。

既存の Agent（bots.py / settings_chat.py）と同じ形の API を、別のテーブルで持つ。
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, delete, func, select

from bt_backend.agents import (
    ChatLine,
    InvalidSettings,
    UnknownAgent,
    get_conversation_agent_info,
    list_conversation_agents,
    propose_settings,
    validate_conversation_settings,
)
from bt_backend.api.schemas import (
    AgentOut,
    BotCreate,
    BotDetail,
    BotFork,
    BotOut,
    SettingsChatIn,
    SettingsChatMessageOut,
    SettingsChatOut,
    VersionCreate,
    VersionOut,
)
from bt_backend.api.settings_chat import HISTORY_LIMIT
from bt_backend.config import get_settings
from bt_backend.db import SessionDep
from bt_backend.models import (
    ConversationBot,
    ConversationBotSettingsChatMessage,
    ConversationBotVersion,
)

router = APIRouter(prefix="/api", tags=["conversation-bots"])

NOT_FOUND = "会話用エージェントが見つかりません"


def latest_version(session: Session, bot_id: int) -> int | None:
    query = select(func.max(ConversationBotVersion.version)).where(
        ConversationBotVersion.bot_id == bot_id
    )
    return session.exec(query).one()


def agent_name(agent_id: str) -> str:
    try:
        return get_conversation_agent_info(agent_id).name
    except UnknownAgent:
        return f"（不明な AgentCore: {agent_id}）"


def _bot_out(session: Session, bot: ConversationBot) -> BotOut:
    assert bot.id is not None
    origin = (
        session.get(ConversationBot, bot.forked_from_bot_id) if bot.forked_from_bot_id else None
    )
    return BotOut(
        **bot.model_dump(),
        agent_name=agent_name(bot.agent_id),
        forked_from_bot_name=origin.name if origin else None,
        latest_version=latest_version(session, bot.id),
    )


def _version_out(v: ConversationBotVersion) -> VersionOut:
    return VersionOut.model_validate(v, from_attributes=True)


def _validate(agent_id: str, settings: dict[str, Any]) -> None:
    try:
        validate_conversation_settings(agent_id, settings)
    except UnknownAgent as e:
        raise HTTPException(400, f"AgentCore が見つかりません: {agent_id}") from e
    except InvalidSettings as e:
        raise HTTPException(400, f"設定が正しくありません:\n{e}") from e


def _bot(session: Session, bot_id: int) -> ConversationBot:
    bot = session.get(ConversationBot, bot_id)
    if bot is None:
        raise HTTPException(404, NOT_FOUND)
    return bot


@router.get("/conversation-agents")
def get_agents() -> list[AgentOut]:
    return [AgentOut.model_validate(a, from_attributes=True) for a in list_conversation_agents()]


@router.get("/conversation-bots")
def list_bots(session: SessionDep) -> list[BotOut]:
    bots = session.exec(select(ConversationBot).order_by(col(ConversationBot.id))).all()
    return [_bot_out(session, b) for b in bots]


@router.post("/conversation-bots")
def create_bot(body: BotCreate, session: SessionDep) -> BotDetail:
    _validate(body.agent_id, body.settings)
    bot = ConversationBot(name=body.name, agent_id=body.agent_id)
    session.add(bot)
    session.flush()
    assert bot.id is not None
    session.add(
        ConversationBotVersion(bot_id=bot.id, version=1, settings=body.settings, note=body.note)
    )
    session.commit()
    return get_bot(bot.id, session)


@router.get("/conversation-bots/{bot_id}")
def get_bot(bot_id: int, session: SessionDep) -> BotDetail:
    bot = _bot(session, bot_id)
    versions = session.exec(
        select(ConversationBotVersion)
        .where(ConversationBotVersion.bot_id == bot_id)
        .order_by(col(ConversationBotVersion.version))
    ).all()
    return BotDetail(
        **_bot_out(session, bot).model_dump(), versions=[_version_out(v) for v in versions]
    )


@router.post("/conversation-bots/{bot_id}/fork")
def fork_bot(bot_id: int, body: BotFork, session: SessionDep) -> BotDetail:
    """名前を変えて保存する。元はそのままに、新しい会話用エージェントを v1 から作る。"""
    origin = _bot(session, bot_id)
    if body.name == origin.name:
        raise HTTPException(
            400, "名前を変えずに保存する場合は、新しいバージョンとして保存してください"
        )
    _validate(origin.agent_id, body.settings)
    bot = ConversationBot(
        name=body.name,
        agent_id=origin.agent_id,
        forked_from_bot_id=bot_id,
        forked_from_version=body.base_version,
    )
    session.add(bot)
    session.flush()
    assert bot.id is not None
    session.add(
        ConversationBotVersion(bot_id=bot.id, version=1, settings=body.settings, note=body.note)
    )
    session.commit()
    return get_bot(bot.id, session)


@router.post("/conversation-bots/{bot_id}/versions")
def create_version(bot_id: int, body: VersionCreate, session: SessionDep) -> VersionOut:
    bot = _bot(session, bot_id)
    _validate(bot.agent_id, body.settings)
    version = ConversationBotVersion(
        bot_id=bot_id,
        version=(latest_version(session, bot_id) or 0) + 1,
        settings=body.settings,
        note=body.note,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return _version_out(version)


def _chat_out(m: ConversationBotSettingsChatMessage) -> SettingsChatMessageOut:
    return SettingsChatMessageOut.model_validate(m, from_attributes=True)


def _chat_messages(session: Session, bot_id: int) -> list[ConversationBotSettingsChatMessage]:
    return list(
        session.exec(
            select(ConversationBotSettingsChatMessage)
            .where(ConversationBotSettingsChatMessage.bot_id == bot_id)
            .order_by(col(ConversationBotSettingsChatMessage.id))
        )
    )


@router.get("/conversation-bots/{bot_id}/settings-chat")
def get_settings_chat(bot_id: int, session: SessionDep) -> list[SettingsChatMessageOut]:
    _bot(session, bot_id)
    return [_chat_out(m) for m in _chat_messages(session, bot_id)]


@router.delete("/conversation-bots/{bot_id}/settings-chat")
def clear_settings_chat(bot_id: int, session: SessionDep) -> None:
    _bot(session, bot_id)
    session.exec(
        delete(ConversationBotSettingsChatMessage).where(
            col(ConversationBotSettingsChatMessage.bot_id) == bot_id
        )
    )
    session.commit()


@router.post("/conversation-bots/{bot_id}/settings-chat")
def post_settings_chat(bot_id: int, body: SettingsChatIn, session: SessionDep) -> SettingsChatOut:
    """要望を送り、設定の変更案を受け取る。案は保存しない（画面の編集中の設定に反映する）。"""
    bot = _bot(session, bot_id)
    try:
        get_conversation_agent_info(bot.agent_id)
    except UnknownAgent as e:
        raise HTTPException(400, f"AgentCore が見つかりません: {bot.agent_id}") from e

    history = [
        ChatLine(role=m.role, content=m.content)
        for m in _chat_messages(session, bot_id)
        if m.role in ("user", "assistant")
    ][-HISTORY_LIMIT:]
    user = ConversationBotSettingsChatMessage(bot_id=bot_id, role="user", content=body.message)
    session.add(user)
    session.commit()

    try:
        proposal = propose_settings(
            bot.agent_id,
            body.current_settings,
            history,
            body.message,
            get_settings().anthropic_api_key,
            conversation=True,
        )
        reply = ConversationBotSettingsChatMessage(
            bot_id=bot_id,
            role="assistant",
            content=proposal.reply,
            proposed_settings=proposal.settings,
        )
    except Exception as e:  # noqa: BLE001 - 失敗の内容を履歴に残して画面に返す
        reply = ConversationBotSettingsChatMessage(
            bot_id=bot_id, role="error", content=f"{type(e).__name__}: {e}"
        )
    session.add(reply)
    session.commit()
    session.refresh(user)
    session.refresh(reply)
    return SettingsChatOut(
        messages=[_chat_out(user), _chat_out(reply)], proposed_settings=reply.proposed_settings
    )
