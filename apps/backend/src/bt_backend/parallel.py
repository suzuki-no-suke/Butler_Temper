"""並行会話。会話の途中から、同じ入力への応答（候補）を何パターンも作り、一つを採用して続ける。

- 分かれる位置までの発言は、並行会話に写して持つ（元の会話をたどらずに済むように）
- 候補は Agent の 1 ターン分の結果で、会話とは別に持つ。採用しなかった候補も消さない
- 候補を作る中で呼んだシミュレータの実行記録は、候補に結びつけて残す
- 会話をまたぐ記録は、候補を採用したときにだけ書く
- 割込み要求は、今は候補に伝えない
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, col, select

from bt_backend.agents import ChatTurn, run_turn
from bt_backend.continuations import continuation_access, save_continuations
from bt_backend.db import get_engine, get_raw_engine
from bt_backend.models import (
    Bot,
    BotVersion,
    Conversation,
    Dialogue,
    DialogueMessage,
    Message,
    ParallelCandidate,
    ParallelConversation,
    ParallelMessage,
    ParallelRound,
    ParallelSettingsRow,
    utcnow,
)
from bt_backend.raw_models import RawCall
from bt_backend.services import ConversationClosed, api_keys, messages_of
from bt_backend.simulations import Caller, access_for
from bt_backend.snapshot import current_source_hash

SETTINGS_ROW_ID = 1
# 1 回で作れる候補の数の上限
MAX_CANDIDATES = 50


class ParallelSettings(BaseModel):
    """並行会話の設定。画面から変える。バージョン管理はしない。"""

    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(default=3, ge=1, le=20, description="候補を同時に作る数")


class InvalidBranch(Exception):
    pass


def parallel_settings(session: Session) -> ParallelSettings:
    row = session.get(ParallelSettingsRow, SETTINGS_ROW_ID)
    return ParallelSettings.model_validate(row.values if row else {})


def save_parallel_settings(session: Session, settings: ParallelSettings) -> None:
    row = session.get(ParallelSettingsRow, SETTINGS_ROW_ID) or ParallelSettingsRow(
        id=SETTINGS_ROW_ID, values={}
    )
    row.values = settings.model_dump()
    row.updated_at = utcnow()
    session.add(row)
    session.commit()


def parallel_messages(session: Session, parallel_id: int) -> list[ParallelMessage]:
    return list(
        session.exec(
            select(ParallelMessage)
            .where(ParallelMessage.parallel_conversation_id == parallel_id)
            .order_by(col(ParallelMessage.seq))
        )
    )


def rounds_of(session: Session, parallel_id: int) -> list[ParallelRound]:
    return list(
        session.exec(
            select(ParallelRound)
            .where(ParallelRound.parallel_conversation_id == parallel_id)
            .order_by(col(ParallelRound.id))
        )
    )


def candidates_of(session: Session, round_id: int) -> list[ParallelCandidate]:
    return list(
        session.exec(
            select(ParallelCandidate)
            .where(ParallelCandidate.round_id == round_id)
            .order_by(col(ParallelCandidate.index))
        )
    )


def _create(
    session: Session,
    parallel: ParallelConversation,
    copied: list[tuple[str, str, Any]],
) -> ParallelConversation:
    """copied は（役, 本文, 元の発言）の並び。元の発言から RAW・内訳・状態・日時を写す。"""
    session.add(parallel)
    session.flush()
    assert parallel.id is not None
    for seq, (role, content, m) in enumerate(copied):
        session.add(
            ParallelMessage(
                parallel_conversation_id=parallel.id,
                seq=seq,
                role=role,
                content=content,
                raw_call_id=m.raw_call_id,
                parts=m.parts if role == "assistant" else None,
                agent_state=m.agent_state if role == "assistant" else None,
                created_at=m.created_at,
            )
        )
    session.commit()
    session.refresh(parallel)
    return parallel


def start_from_conversation(
    session: Session, conversation: Conversation, message_id: int
) -> ParallelConversation:
    """会話の、指定した Agent の発言までを写した並行会話を作る。"""
    assert conversation.id is not None
    messages = [m for m in messages_of(session, conversation.id) if m.role in ("user", "assistant")]
    target = next((m for m in messages if m.id == message_id), None)
    if target is None or target.role != "assistant":
        raise InvalidBranch("分かれる位置は、この会話の Agent の発言から選んでください")
    copied = [(m.role, m.content, m) for m in messages if m.seq <= target.seq]
    parallel = ParallelConversation(
        bot_id=conversation.bot_id,
        bot_version_id=conversation.bot_version_id,
        source_kind="conversation",
        source_conversation_id=conversation.id,
        agent_state=target.agent_state,
    )
    return _create(session, parallel, copied)


def start_from_dialogue(
    session: Session, dialogue: Dialogue, message_id: int
) -> ParallelConversation:
    """エージェント間対話の、指定した Agent の発言までを写した並行会話を作る。

    会話用エージェントの発言は利用者の発言として写す。以後は利用者が入力する。
    """
    speeches = list(
        session.exec(
            select(DialogueMessage)
            .where(DialogueMessage.dialogue_id == dialogue.id)
            .where(DialogueMessage.role == "speech")
            .order_by(col(DialogueMessage.seq))
        )
    )
    target = next((m for m in speeches if m.id == message_id), None)
    if target is None or target.speaker != "agent":
        raise InvalidBranch("分かれる位置は、この対話の Agent の発言から選んでください")
    copied = [
        ("assistant" if m.speaker == "agent" else "user", m.content, m)
        for m in speeches
        if m.seq <= target.seq
    ]
    parallel = ParallelConversation(
        bot_id=dialogue.bot_id,
        bot_version_id=dialogue.bot_version_id,
        source_kind="dialogue",
        source_dialogue_id=dialogue.id,
        agent_state=target.agent_state,
    )
    return _create(session, parallel, copied)


def start_new(session: Session, bot: Bot) -> ParallelConversation:
    """会話の最初から並行会話を始める。Agent の最新のバージョンに固定する。"""
    if bot.unavailable_reason:
        raise ConversationClosed(f"この Agent は停止しています: {bot.unavailable_reason}")
    version = session.exec(
        select(BotVersion)
        .where(BotVersion.bot_id == bot.id)
        .order_by(col(BotVersion.version).desc())
    ).first()
    assert bot.id is not None and version is not None and version.id is not None
    parallel = ParallelConversation(bot_id=bot.id, bot_version_id=version.id, source_kind="new")
    return _create(session, parallel, [])


def create_round(
    session: Session, parallel: ParallelConversation, content: str, count: int
) -> ParallelRound:
    """候補を作る回を用意する。候補を作るのは run_round。"""
    bot = session.get(Bot, parallel.bot_id)
    assert bot is not None and parallel.id is not None
    if bot.unavailable_reason:
        raise ConversationClosed(f"この Agent は停止しています: {bot.unavailable_reason}")
    round_ = ParallelRound(parallel_conversation_id=parallel.id, content=content, count=count)
    session.add(round_)
    session.flush()
    assert round_.id is not None
    for i in range(count):
        session.add(ParallelCandidate(round_id=round_.id, index=i))
    session.commit()
    session.refresh(round_)
    return round_


def run_round(round_id: int) -> None:
    """回の候補を、設定の数ずつ並行に作る。候補ごとに DB の接続を分ける。"""
    with Session(get_engine()) as session:
        concurrency = parallel_settings(session).concurrency
        ids = [c.id for c in candidates_of(session, round_id) if c.status == "pending"]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(_run_candidate, ids))


def _run_candidate(candidate_id: int | None) -> None:
    assert candidate_id is not None
    with Session(get_engine()) as session, Session(get_raw_engine()) as raw_session:
        candidate = session.get(ParallelCandidate, candidate_id)
        assert candidate is not None
        round_ = session.get(ParallelRound, candidate.round_id)
        assert round_ is not None
        parallel = session.get(ParallelConversation, round_.parallel_conversation_id)
        assert parallel is not None and parallel.id is not None
        bot = session.get(Bot, parallel.bot_id)
        version = session.get(BotVersion, parallel.bot_version_id)
        assert bot is not None and version is not None and bot.id is not None
        candidate.status = "running"
        session.add(candidate)
        session.commit()

        copied = parallel_messages(session, parallel.id)
        turns = [
            ChatTurn(
                seq=m.seq,
                role="user" if m.role == "user" else "assistant",
                content=m.content,
                parts=m.parts if m.role == "assistant" else None,
            )
            for m in copied
        ] + [ChatTurn(seq=len(copied), role="user", content=round_.content)]
        raw = RawCall(
            parallel_candidate_id=candidate_id,
            agent_id=bot.agent_id,
            source_hash=current_source_hash(),
            exchanges=[],
        )
        caller = Caller(kind="parallel", agent_id=bot.agent_id, parallel_candidate_id=candidate_id)
        outcome = run_turn(
            bot.agent_id,
            version.settings,
            turns,
            dict(parallel.agent_state or {}),
            api_keys(),
            [],
            access_for(session, raw_session, caller, api_keys()),
            continuation_access(session, bot.id),
        )
        raw.exchanges = outcome.exchanges
        raw.error = outcome.error
        raw.finished_at = utcnow()
        raw_session.add(raw)
        raw_session.commit()

        candidate.raw_call_id = raw.id
        candidate.finished_at = utcnow()
        if outcome.error is None:
            candidate.status = "succeeded"
            candidate.text = outcome.text or ""
            candidate.parts = outcome.parts
            candidate.agent_state = outcome.state
            candidate.continuations = outcome.continuations or None
        else:
            candidate.status = "failed"
            candidate.error = outcome.error
            if outcome.model_unavailable:
                bot.unavailable_reason = "モデルが見つかりません（API が 404 を返しました）"
                session.add(bot)
        session.add(candidate)
        session.commit()


def adopt(session: Session, candidate: ParallelCandidate) -> Conversation:
    """候補を採用し、写した発言・利用者の入力・候補の応答を持つ新しい会話を作る。

    同じ候補を何度採用してもよい（そのたびに新しい会話になる）。
    """
    if candidate.status != "succeeded":
        raise InvalidBranch("応答を作れた候補だけを採用できます")
    round_ = session.get(ParallelRound, candidate.round_id)
    assert round_ is not None
    parallel = session.get(ParallelConversation, round_.parallel_conversation_id)
    assert parallel is not None and parallel.id is not None
    conversation = Conversation(
        bot_id=parallel.bot_id,
        bot_version_id=parallel.bot_version_id,
        parallel_candidate_id=candidate.id,
        agent_state=candidate.agent_state,
    )
    session.add(conversation)
    session.flush()
    assert conversation.id is not None
    copied = parallel_messages(session, parallel.id)
    for m in copied:
        session.add(
            Message(
                conversation_id=conversation.id,
                seq=m.seq,
                role=m.role,
                content=m.content,
                raw_call_id=m.raw_call_id,
                parts=m.parts,
                agent_state=m.agent_state,
                created_at=m.created_at,
            )
        )
    seq = len(copied)
    session.add(
        Message(
            conversation_id=conversation.id,
            seq=seq,
            role="user",
            content=round_.content,
            created_at=round_.created_at,
        )
    )
    session.add(
        Message(
            conversation_id=conversation.id,
            seq=seq + 1,
            role="assistant",
            content=candidate.text or "",
            raw_call_id=candidate.raw_call_id,
            parts=candidate.parts,
            agent_state=candidate.agent_state,
            created_at=candidate.finished_at or utcnow(),
        )
    )
    session.commit()
    if candidate.continuations:
        save_continuations(
            session, parallel.bot_id, candidate.continuations, conversation_id=conversation.id
        )
    session.refresh(conversation)
    return conversation


def adopted_conversations(session: Session, candidate_ids: list[int]) -> dict[int, list[int]]:
    """候補ごとの、その候補を採用して作った会話の id。"""
    out: dict[int, list[int]] = {}
    for c in session.exec(
        select(Conversation)
        .where(col(Conversation.parallel_candidate_id).in_(candidate_ids))
        .order_by(col(Conversation.id))
    ):
        assert c.parallel_candidate_id is not None and c.id is not None
        out.setdefault(c.parallel_candidate_id, []).append(c.id)
    return out
