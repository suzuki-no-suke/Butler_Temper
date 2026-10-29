from fastapi import APIRouter, HTTPException
from sqlmodel import select

from bt_backend.api.schemas import (
    ConversationCommentIn,
    ConversationCommentOut,
    MessageCommentIn,
    MessageCommentOut,
)
from bt_backend.db import SessionDep
from bt_backend.models import (
    Conversation,
    ConversationComment,
    Message,
    MessageComment,
    utcnow,
)

router = APIRouter(prefix="/api", tags=["comments"])


def _assistant_message(session: SessionDep, message_id: int) -> Message:
    message = session.get(Message, message_id)
    if message is None:
        raise HTTPException(404, "発言が見つかりません")
    if message.role != "assistant":
        raise HTTPException(400, "評価できるのは BOT の回答だけです")
    return message


@router.put("/messages/{message_id}/comment")
def put_message_comment(
    message_id: int, body: MessageCommentIn, session: SessionDep
) -> MessageCommentOut:
    _assistant_message(session, message_id)
    comment = session.exec(
        select(MessageComment).where(MessageComment.message_id == message_id)
    ).first()
    if comment is None:
        comment = MessageComment(message_id=message_id, rating=body.rating, text=body.text)
    else:
        comment.rating = body.rating
        comment.text = body.text
        comment.updated_at = utcnow()
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return MessageCommentOut.model_validate(comment, from_attributes=True)


@router.delete("/messages/{message_id}/comment")
def delete_message_comment(message_id: int, session: SessionDep) -> None:
    comment = session.exec(
        select(MessageComment).where(MessageComment.message_id == message_id)
    ).first()
    if comment is not None:
        session.delete(comment)
        session.commit()


@router.post("/conversations/{conversation_id}/comments")
def add_conversation_comment(
    conversation_id: int, body: ConversationCommentIn, session: SessionDep
) -> ConversationCommentOut:
    if session.get(Conversation, conversation_id) is None:
        raise HTTPException(404, "会話が見つかりません")
    if body.rating is None and body.text.strip() == "":
        raise HTTPException(400, "評価かコメントのどちらかを入れてください")
    comment = ConversationComment(
        conversation_id=conversation_id, rating=body.rating, text=body.text
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return ConversationCommentOut.model_validate(comment, from_attributes=True)


@router.delete("/conversation-comments/{comment_id}")
def delete_conversation_comment(comment_id: int, session: SessionDep) -> None:
    comment = session.get(ConversationComment, comment_id)
    if comment is None:
        raise HTTPException(404, "コメントが見つかりません")
    session.delete(comment)
    session.commit()
