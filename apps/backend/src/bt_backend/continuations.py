"""会話をまたぐ記録。Agent が TurnResult.continuations に入れたものを、Bot ごとに保存する。"""

from typing import Any

from sqlmodel import Session, select

from bt_backend.agents import ContinuationAccess
from bt_backend.models import ContinuationRecord, utcnow


def _find(session: Session, bot_id: int, key: str) -> ContinuationRecord | None:
    return session.exec(
        select(ContinuationRecord)
        .where(ContinuationRecord.bot_id == bot_id)
        .where(ContinuationRecord.key == key)
    ).first()


def continuation_access(session: Session, bot_id: int) -> ContinuationAccess:
    """同じ Bot（名前が同じならバージョン違いを含む）の記録を読む口。"""

    def get(key: str) -> dict[str, Any] | None:
        record = _find(session, bot_id, key)
        return dict(record.data) if record else None

    return ContinuationAccess(get=get)


def save_continuations(
    session: Session,
    bot_id: int,
    records: dict[str, dict[str, Any]],
    conversation_id: int | None = None,
    dialogue_id: int | None = None,
) -> None:
    """記録を書く。同じキーがあれば中身を置き換える。"""
    for key, data in records.items():
        record = _find(session, bot_id, key) or ContinuationRecord(bot_id=bot_id, key=key, data={})
        record.data = data
        record.conversation_id = conversation_id
        record.dialogue_id = dialogue_id
        record.updated_at = utcnow()
        session.add(record)
    session.commit()
