from fastapi import APIRouter, HTTPException
from sqlmodel import col, delete, select

from bt_backend.agents import ChatLine, UnknownAgent, get_agent_info, propose_settings
from bt_backend.api.schemas import SettingsChatIn, SettingsChatMessageOut, SettingsChatOut
from bt_backend.config import get_settings
from bt_backend.db import SessionDep
from bt_backend.models import Bot, SettingsChatMessage

router = APIRouter(prefix="/api", tags=["settings-chat"])

# 設定変更チャットに渡す、直近のやり取りの数
HISTORY_LIMIT = 20


def _out(m: SettingsChatMessage) -> SettingsChatMessageOut:
    return SettingsChatMessageOut.model_validate(m, from_attributes=True)


def _messages(session: SessionDep, bot_id: int) -> list[SettingsChatMessage]:
    return list(
        session.exec(
            select(SettingsChatMessage)
            .where(SettingsChatMessage.bot_id == bot_id)
            .order_by(col(SettingsChatMessage.id))
        )
    )


def _bot(session: SessionDep, bot_id: int) -> Bot:
    bot = session.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(404, "BOT が見つかりません")
    return bot


@router.get("/bots/{bot_id}/settings-chat")
def get_settings_chat(bot_id: int, session: SessionDep) -> list[SettingsChatMessageOut]:
    _bot(session, bot_id)
    return [_out(m) for m in _messages(session, bot_id)]


@router.delete("/bots/{bot_id}/settings-chat")
def clear_settings_chat(bot_id: int, session: SessionDep) -> None:
    _bot(session, bot_id)
    session.exec(delete(SettingsChatMessage).where(col(SettingsChatMessage.bot_id) == bot_id))
    session.commit()


@router.post("/bots/{bot_id}/settings-chat")
def post_settings_chat(bot_id: int, body: SettingsChatIn, session: SessionDep) -> SettingsChatOut:
    """要望を送り、設定の変更案を受け取る。案は保存しない（画面の編集中の設定に反映する）。"""
    bot = _bot(session, bot_id)
    try:
        get_agent_info(bot.agent_id)
    except UnknownAgent as e:
        raise HTTPException(400, f"Agent が見つかりません: {bot.agent_id}") from e

    history = [
        ChatLine(role=m.role, content=m.content)
        for m in _messages(session, bot_id)
        if m.role in ("user", "assistant")
    ][-HISTORY_LIMIT:]
    user = SettingsChatMessage(bot_id=bot_id, role="user", content=body.message)
    session.add(user)
    session.commit()

    try:
        proposal = propose_settings(
            bot.agent_id,
            body.current_settings,
            history,
            body.message,
            get_settings().anthropic_api_key,
        )
        reply = SettingsChatMessage(
            bot_id=bot_id,
            role="assistant",
            content=proposal.reply,
            proposed_settings=proposal.settings,
        )
    except Exception as e:  # noqa: BLE001 - 失敗の内容を履歴に残して画面に返す
        reply = SettingsChatMessage(bot_id=bot_id, role="error", content=f"{type(e).__name__}: {e}")
    session.add(reply)
    session.commit()
    session.refresh(user)
    session.refresh(reply)
    return SettingsChatOut(
        messages=[_out(user), _out(reply)], proposed_settings=reply.proposed_settings
    )
