"""並行会話。会話・エージェント間対話の途中から、同じ入力への応答（候補）を何パターンも作る。"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlmodel import Session, col, select

from bt_backend.api.conversations import PREVIEW_CHARS, _conversation_out
from bt_backend.api.schemas import (
    ConversationOut,
    MessageOut,
    ParallelCandidateOut,
    ParallelConversationDetail,
    ParallelConversationOut,
    ParallelNew,
    ParallelRoundCreate,
    ParallelRoundOut,
    ParallelStart,
)
from bt_backend.db import SessionDep
from bt_backend.models import (
    Bot,
    BotVersion,
    Conversation,
    Dialogue,
    ParallelCandidate,
    ParallelConversation,
)
from bt_backend.parallel import (
    InvalidBranch,
    ParallelSettings,
    adopt,
    adopted_conversations,
    candidates_of,
    create_round,
    parallel_messages,
    parallel_settings,
    rounds_of,
    run_round,
    save_parallel_settings,
    start_from_conversation,
    start_from_dialogue,
    start_new,
)
from bt_backend.services import ConversationClosed

router = APIRouter(prefix="/api", tags=["parallel"])


def _get(session: Session, parallel_id: int) -> ParallelConversation:
    p = session.get(ParallelConversation, parallel_id)
    if p is None:
        raise HTTPException(404, "並行会話が見つかりません")
    return p


def _out(session: Session, p: ParallelConversation) -> ParallelConversationOut:
    bot = session.get(Bot, p.bot_id)
    version = session.get(BotVersion, p.bot_version_id)
    assert bot is not None and version is not None and p.id is not None
    messages = parallel_messages(session, p.id)
    return ParallelConversationOut(
        id=p.id,
        bot_id=p.bot_id,
        bot_name=bot.name,
        bot_version=version.version,
        source_kind=p.source_kind,
        created_at=p.created_at,
        message_count=len(messages),
        round_count=len(rounds_of(session, p.id)),
        preview=messages[-1].content[:PREVIEW_CHARS] if messages else "",
    )


@router.post("/conversations/{conversation_id}/parallel")
def start_from_conversation_api(
    conversation_id: int, body: ParallelStart, session: SessionDep
) -> ParallelConversationOut:
    c = session.get(Conversation, conversation_id)
    if c is None:
        raise HTTPException(404, "会話が見つかりません")
    try:
        return _out(session, start_from_conversation(session, c, body.message_id))
    except InvalidBranch as e:
        raise HTTPException(422, str(e)) from e


@router.post("/dialogues/{dialogue_id}/parallel")
def start_from_dialogue_api(
    dialogue_id: int, body: ParallelStart, session: SessionDep
) -> ParallelConversationOut:
    d = session.get(Dialogue, dialogue_id)
    if d is None:
        raise HTTPException(404, "エージェント間対話が見つかりません")
    try:
        return _out(session, start_from_dialogue(session, d, body.message_id))
    except InvalidBranch as e:
        raise HTTPException(422, str(e)) from e


@router.post("/parallel-conversations")
def start_new_api(body: ParallelNew, session: SessionDep) -> ParallelConversationOut:
    """会話の最初から並行会話を始める。"""
    bot = session.get(Bot, body.bot_id)
    if bot is None:
        raise HTTPException(404, "Agent が見つかりません")
    try:
        return _out(session, start_new(session, bot))
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e


@router.get("/parallel-conversations")
def list_parallel(session: SessionDep) -> list[ParallelConversationOut]:
    query = select(ParallelConversation).order_by(col(ParallelConversation.id).desc())
    return [_out(session, p) for p in session.exec(query)]


@router.get("/parallel-conversations/{parallel_id}")
def get_parallel(parallel_id: int, session: SessionDep) -> ParallelConversationDetail:
    p = _get(session, parallel_id)
    rounds = rounds_of(session, parallel_id)
    candidates = {r.id: candidates_of(session, r.id or 0) for r in rounds}
    adopted = adopted_conversations(
        session, [c.id for cs in candidates.values() for c in cs if c.id is not None]
    )
    return ParallelConversationDetail(
        **_out(session, p).model_dump(),
        messages=[
            MessageOut.model_validate(m, from_attributes=True)
            for m in parallel_messages(session, parallel_id)
        ],
        rounds=[
            ParallelRoundOut(
                id=r.id or 0,
                content=r.content,
                count=r.count,
                created_at=r.created_at,
                candidates=[
                    ParallelCandidateOut(
                        **c.model_dump(exclude={"round_id", "continuations"}),
                        conversation_ids=adopted.get(c.id or 0, []),
                    )
                    for c in candidates[r.id]
                ],
            )
            for r in rounds
        ],
    )


@router.post("/parallel-conversations/{parallel_id}/rounds")
def create_round_api(
    parallel_id: int,
    body: ParallelRoundCreate,
    session: SessionDep,
    background: BackgroundTasks,
) -> ParallelRoundOut:
    """候補を作る回を用意して、すぐに返す。候補は裏で作り、できたものから詳細に出る。"""
    p = _get(session, parallel_id)
    try:
        r = create_round(session, p, body.content, body.count)
    except ConversationClosed as e:
        raise HTTPException(409, str(e)) from e
    assert r.id is not None
    background.add_task(run_round, r.id)
    return ParallelRoundOut(
        id=r.id,
        content=r.content,
        count=r.count,
        created_at=r.created_at,
        candidates=[
            ParallelCandidateOut(
                **c.model_dump(exclude={"round_id", "continuations"}), conversation_ids=[]
            )
            for c in candidates_of(session, r.id)
        ],
    )


@router.post("/parallel-candidates/{candidate_id}/adopt")
def adopt_api(candidate_id: int, session: SessionDep) -> ConversationOut:
    """候補を採用して、新しい会話を作る。同じ候補を何度採用してもよい。"""
    c = session.get(ParallelCandidate, candidate_id)
    if c is None:
        raise HTTPException(404, "候補が見つかりません")
    try:
        return _conversation_out(session, adopt(session, c))
    except InvalidBranch as e:
        raise HTTPException(409, str(e)) from e


@router.get("/parallel-settings")
def get_parallel_settings(session: SessionDep) -> ParallelSettings:
    return parallel_settings(session)


@router.put("/parallel-settings")
def put_parallel_settings(body: ParallelSettings, session: SessionDep) -> ParallelSettings:
    save_parallel_settings(session, body)
    return parallel_settings(session)
