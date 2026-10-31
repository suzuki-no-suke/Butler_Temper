"""エージェント間対話の進行。会話用エージェントと Agent を交互に呼び、結果を保存する。

1 ターンは、会話用エージェントの発言と、それへの Agent の応答の一組とする。
会話用エージェントは人間と同じく発言の文だけを出し、Agent はそれを利用者の発言として受け取る。
"""

import unicodedata

from sqlmodel import Session, col, select

from bt_backend.agents import ChatTurn, TurnOutcome, run_conversation_turn, run_turn
from bt_backend.models import (
    Bot,
    BotVersion,
    ConversationBot,
    ConversationBotVersion,
    Dialogue,
    DialogueMessage,
    TemplateVersion,
    utcnow,
)
from bt_backend.raw_models import RawCall
from bt_backend.services import ConversationClosed, api_keys
from bt_backend.simulations import Caller, access_for, link_runs
from bt_backend.snapshot import current_source_hash

NOT_FOUND = "モデルが見つかりません（API が 404 を返しました）"


def sanitize_template(text: str) -> str:
    """テンプレートの本文を保存できる形にする。

    改行を LF にそろえ、改行とタブ以外の制御文字を除く。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(c for c in text if c in "\n\t" or unicodedata.category(c) != "Cc")


def dialogue_messages(session: Session, dialogue_id: int) -> list[DialogueMessage]:
    return list(
        session.exec(
            select(DialogueMessage)
            .where(DialogueMessage.dialogue_id == dialogue_id)
            .order_by(col(DialogueMessage.seq))
        )
    )


def dialogue_templates(session: Session, dialogue: Dialogue) -> dict[str, str]:
    templates: dict[str, str] = {}
    for name, version_id in dialogue.template_version_ids.items():
        version = session.get(TemplateVersion, version_id)
        assert version is not None
        templates[name] = version.content
    return templates


def _turns(speeches: list[DialogueMessage], me: str) -> list[ChatTurn]:
    """発言者 me から見た会話。自分の発言が assistant、相手の発言が user になる。"""
    return [
        ChatTurn(
            seq=m.seq,
            role="assistant" if m.speaker == me else "user",
            content=m.content,
            parts=m.parts if m.speaker == me else None,
        )
        for m in speeches
    ]


def _bots(
    session: Session, dialogue: Dialogue
) -> tuple[ConversationBot, ConversationBotVersion, Bot, BotVersion]:
    cbot = session.get(ConversationBot, dialogue.conversation_bot_id)
    cversion = session.get(ConversationBotVersion, dialogue.conversation_bot_version_id)
    bot = session.get(Bot, dialogue.bot_id)
    version = session.get(BotVersion, dialogue.bot_version_id)
    assert cbot is not None and cversion is not None and bot is not None and version is not None
    return cbot, cversion, bot, version


def _check_available(cbot: ConversationBot, bot: Bot) -> None:
    if cbot.unavailable_reason:
        raise ConversationClosed(
            f"この会話用エージェントは停止しています: {cbot.unavailable_reason}"
        )
    if bot.unavailable_reason:
        raise ConversationClosed(f"この Agent は停止しています: {bot.unavailable_reason}")


def _save_raw(
    raw_session: Session, dialogue_id: int, agent_id: str, outcome: TurnOutcome
) -> RawCall:
    raw = RawCall(
        dialogue_id=dialogue_id,
        agent_id=agent_id,
        source_hash=current_source_hash(),
        exchanges=outcome.exchanges,
        error=outcome.error,
        finished_at=utcnow(),
    )
    raw_session.add(raw)
    raw_session.commit()
    return raw


def advance_dialogue(
    session: Session, raw_session: Session, dialogue: Dialogue
) -> list[DialogueMessage]:
    """1 ターン進める。保存した発言（またはエラー）を返す。エラーが起きたら保存して止める。"""
    if dialogue.status != "active":
        raise ConversationClosed("このエージェント間対話はエラーで停止しています")
    assert dialogue.id is not None
    dialogue_id = dialogue.id
    cbot, cversion, bot, version = _bots(session, dialogue)
    _check_available(cbot, bot)

    speeches = [m for m in dialogue_messages(session, dialogue_id) if m.role == "speech"]
    seq = len(dialogue_messages(session, dialogue_id))
    saved: list[DialogueMessage] = []

    def stop(
        speaker: str, outcome: TurnOutcome, raw: RawCall, owner: Bot | ConversationBot
    ) -> None:
        saved.append(
            DialogueMessage(
                dialogue_id=dialogue_id,
                seq=seq + len(saved),
                speaker=speaker,
                role="error",
                content=outcome.error or "",
                raw_call_id=raw.id,
            )
        )
        dialogue.status = "stopped"
        if outcome.model_unavailable:
            owner.unavailable_reason = NOT_FOUND
            session.add(owner)

    # どちらの発言者も、シミュレータを使える。呼んだ記録は、その発言者の発言に結びつける
    callers = {
        "conversation": Caller(kind="dialogue", agent_id=cbot.agent_id, dialogue_id=dialogue_id),
        "agent": Caller(kind="dialogue", agent_id=bot.agent_id, dialogue_id=dialogue_id),
    }

    # 会話用エージェントが発言する
    outcome = run_conversation_turn(
        cbot.agent_id,
        cversion.settings,
        _turns(speeches, "conversation"),
        dict(dialogue.conversation_state or {}),
        api_keys(),
        dialogue_templates(session, dialogue),
        access_for(session, raw_session, callers["conversation"], api_keys()),
    )
    raw = _save_raw(raw_session, dialogue_id, cbot.agent_id, outcome)
    if outcome.error is not None:
        stop("conversation", outcome, raw, cbot)
    else:
        speech = DialogueMessage(
            dialogue_id=dialogue_id,
            seq=seq,
            speaker="conversation",
            role="speech",
            content=outcome.text or "",
            raw_call_id=raw.id,
            agent_state=outcome.state,
        )
        saved.append(speech)
        dialogue.conversation_state = outcome.state

        # Agent が、会話用エージェントの発言を利用者の発言として受けて応答する
        outcome = run_turn(
            bot.agent_id,
            version.settings,
            _turns([*speeches, speech], "agent"),
            dict(dialogue.agent_state or {}),
            api_keys(),
            simulators=access_for(session, raw_session, callers["agent"], api_keys()),
        )
        raw = _save_raw(raw_session, dialogue_id, bot.agent_id, outcome)
        if outcome.error is not None:
            stop("agent", outcome, raw, bot)
        else:
            saved.append(
                DialogueMessage(
                    dialogue_id=dialogue_id,
                    seq=seq + 1,
                    speaker="agent",
                    role="speech",
                    content=outcome.text or "",
                    raw_call_id=raw.id,
                    parts=outcome.parts,
                    agent_state=outcome.state,
                )
            )
            dialogue.agent_state = outcome.state

    for m in saved:
        session.add(m)
    session.add(dialogue)
    session.commit()
    for m in saved:
        if callers[m.speaker].run_ids:
            link_runs(session, callers[m.speaker], dialogue_message_id=m.id)
    for m in saved:
        session.refresh(m)
    return saved


def resume_dialogue(session: Session, dialogue: Dialogue) -> Dialogue:
    """エージェント間対話を続けるための対話を返す。

    止まっていなければそのまま返す。エラーで止まっていれば、同じバージョン（テンプレートを含む）で
    新しい対話を作り、エラーより前の発言と、それぞれの状態を引き継ぐ。
    Agent の応答を得られなかった最後の会話用エージェントの発言は引き継がない
    （ターンの組を保つため）。
    """
    if dialogue.status == "active":
        return dialogue
    assert dialogue.id is not None
    cbot, _, bot, _ = _bots(session, dialogue)
    _check_available(cbot, bot)

    kept = [m for m in dialogue_messages(session, dialogue.id) if m.role == "speech"]
    while kept and kept[-1].speaker == "conversation":
        kept.pop()

    def last_state(speaker: str) -> dict[str, object] | None:
        return next((m.agent_state for m in reversed(kept) if m.speaker == speaker), None)

    resumed = Dialogue(
        conversation_bot_id=dialogue.conversation_bot_id,
        conversation_bot_version_id=dialogue.conversation_bot_version_id,
        bot_id=dialogue.bot_id,
        bot_version_id=dialogue.bot_version_id,
        template_version_ids=dict(dialogue.template_version_ids),
        resumed_from_id=dialogue.id,
        conversation_state=last_state("conversation"),
        agent_state=last_state("agent"),
    )
    session.add(resumed)
    session.flush()
    assert resumed.id is not None
    for seq, m in enumerate(kept):
        session.add(
            DialogueMessage(
                dialogue_id=resumed.id,
                seq=seq,
                speaker=m.speaker,
                role=m.role,
                content=m.content,
                raw_call_id=m.raw_call_id,
                parts=m.parts,
                agent_state=m.agent_state,
                created_at=m.created_at,
            )
        )
    session.commit()
    session.refresh(resumed)
    return resumed
