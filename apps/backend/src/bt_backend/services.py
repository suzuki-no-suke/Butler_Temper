"""会話の進行。Agents を呼び、結果を通常の DB と RAW 用の DB に保存する。"""

from sqlmodel import Session, select

from bt_backend.agents import BotSpec, ChatTurn, run_chat
from bt_backend.config import get_settings
from bt_backend.models import Bot, BotVersion, Conversation, Message, utcnow
from bt_backend.raw_models import RawCall
from bt_backend.snapshot import current_source_hash


class ConversationClosed(Exception):
    pass


def api_keys() -> dict[str, str | None]:
    s = get_settings()
    return {
        "anthropic": s.anthropic_api_key,
        "openai": s.openai_api_key,
        "gemini": s.gemini_api_key,
        "openrouter": s.openrouter_api_key,
    }


def messages_of(session: Session, conversation_id: int) -> list[Message]:
    return list(
        session.exec(
            select(Message).where(Message.conversation_id == conversation_id).order_by("seq")
        )
    )


def send_message(
    session: Session, raw_session: Session, conversation: Conversation, content: str
) -> list[Message]:
    """利用者の発言を保存し、BOT の応答（またはエラー）を保存して返す。"""
    if conversation.status != "active":
        raise ConversationClosed("この会話はエラーで停止しています")
    bot = session.get(Bot, conversation.bot_id)
    version = session.get(BotVersion, conversation.bot_version_id)
    assert bot is not None and version is not None and conversation.id is not None
    if bot.unavailable_reason:
        raise ConversationClosed(f"この BOT は停止しています: {bot.unavailable_reason}")

    history = messages_of(session, conversation.id)
    seq = len(history)
    user_message = Message(conversation_id=conversation.id, seq=seq, role="user", content=content)
    session.add(user_message)
    session.commit()

    turns = [
        ChatTurn(role="user" if m.role == "user" else "assistant", content=m.content)
        for m in history
        if m.role in ("user", "assistant")
    ] + [ChatTurn(role="user", content=content)]
    spec = BotSpec(provider=bot.provider, models=bot.models, settings=version.settings)

    raw = RawCall(
        conversation_id=conversation.id,
        provider=bot.provider,
        model=str(bot.models.get("chat", "")),
        source_hash=current_source_hash(),
        exchanges=[],
    )
    outcome = run_chat(spec, turns, api_keys())
    raw.exchanges = outcome.exchanges
    raw.error = outcome.error
    raw.finished_at = utcnow()
    raw_session.add(raw)
    raw_session.commit()

    if outcome.error is None:
        reply = Message(
            conversation_id=conversation.id,
            seq=seq + 1,
            role="assistant",
            content=outcome.text or "",
            raw_call_id=raw.id,
        )
    else:
        # エラーは保存して止める
        reply = Message(
            conversation_id=conversation.id,
            seq=seq + 1,
            role="error",
            content=outcome.error,
            raw_call_id=raw.id,
        )
        conversation.status = "stopped"
        session.add(conversation)
        if outcome.model_unavailable:
            bot.unavailable_reason = f"モデルが見つかりません（{outcome.model}）"
            session.add(bot)
    session.add(reply)
    session.commit()
    session.refresh(user_message)
    session.refresh(reply)
    return [user_message, reply]
