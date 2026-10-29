from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, func, select

from bt_backend.agents import (
    InvalidSettings,
    UnknownAgent,
    get_agent_info,
    list_agents,
    validate_settings,
)
from bt_backend.api.schemas import (
    AgentOut,
    BotCreate,
    BotDetail,
    BotFork,
    BotOut,
    VersionCreate,
    VersionOut,
)
from bt_backend.db import SessionDep
from bt_backend.models import Bot, BotVersion

router = APIRouter(prefix="/api", tags=["bots"])


def _latest_version(session: Session, bot_id: int) -> int | None:
    query = select(func.max(BotVersion.version)).where(BotVersion.bot_id == bot_id)
    return session.exec(query).one()


def _agent_name(agent_id: str) -> str:
    try:
        return get_agent_info(agent_id).name
    except UnknownAgent:
        return f"（不明な AgentCore: {agent_id}）"


def _bot_out(session: Session, bot: Bot) -> BotOut:
    assert bot.id is not None
    origin = session.get(Bot, bot.forked_from_bot_id) if bot.forked_from_bot_id else None
    return BotOut(
        **bot.model_dump(),
        agent_name=_agent_name(bot.agent_id),
        forked_from_bot_name=origin.name if origin else None,
        latest_version=_latest_version(session, bot.id),
    )


def _version_out(v: BotVersion) -> VersionOut:
    return VersionOut.model_validate(v, from_attributes=True)


def _validate(agent_id: str, settings: dict[str, Any]) -> None:
    try:
        validate_settings(agent_id, settings)
    except UnknownAgent as e:
        raise HTTPException(400, f"AgentCore が見つかりません: {agent_id}") from e
    except InvalidSettings as e:
        raise HTTPException(400, f"設定が正しくありません:\n{e}") from e


@router.get("/agents")
def get_agents() -> list[AgentOut]:
    return [AgentOut.model_validate(a, from_attributes=True) for a in list_agents()]


@router.get("/bots")
def list_bots(session: SessionDep) -> list[BotOut]:
    bots = session.exec(select(Bot).order_by(col(Bot.id))).all()
    return [_bot_out(session, b) for b in bots]


@router.post("/bots")
def create_bot(body: BotCreate, session: SessionDep) -> BotDetail:
    _validate(body.agent_id, body.settings)
    bot = Bot(name=body.name, agent_id=body.agent_id)
    session.add(bot)
    session.flush()
    assert bot.id is not None
    session.add(BotVersion(bot_id=bot.id, version=1, settings=body.settings, note=body.note))
    session.commit()
    return get_bot(bot.id, session)


@router.get("/bots/{bot_id}")
def get_bot(bot_id: int, session: SessionDep) -> BotDetail:
    bot = session.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(404, "Agent が見つかりません")
    versions = session.exec(
        select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(col(BotVersion.version))
    ).all()
    return BotDetail(
        **_bot_out(session, bot).model_dump(), versions=[_version_out(v) for v in versions]
    )


@router.post("/bots/{bot_id}/fork")
def fork_bot(bot_id: int, body: BotFork, session: SessionDep) -> BotDetail:
    """名前を変えて保存する。元の BOT はそのままに、同じ Agent の新しい BOT を v1 から作る。

    元の BOT のバージョンや会話は引き継がない。どこから分かれたかだけを記録する。
    """
    origin = session.get(Bot, bot_id)
    if origin is None:
        raise HTTPException(404, "Agent が見つかりません")
    if body.name == origin.name:
        raise HTTPException(
            400, "名前を変えずに保存する場合は、新しいバージョンとして保存してください"
        )
    _validate(origin.agent_id, body.settings)
    bot = Bot(
        name=body.name,
        agent_id=origin.agent_id,
        forked_from_bot_id=bot_id,
        forked_from_version=body.base_version,
    )
    session.add(bot)
    session.flush()
    assert bot.id is not None
    session.add(BotVersion(bot_id=bot.id, version=1, settings=body.settings, note=body.note))
    session.commit()
    return get_bot(bot.id, session)


@router.post("/bots/{bot_id}/versions")
def create_version(bot_id: int, body: VersionCreate, session: SessionDep) -> VersionOut:
    bot = session.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(404, "Agent が見つかりません")
    _validate(bot.agent_id, body.settings)
    version = BotVersion(
        bot_id=bot_id,
        version=(_latest_version(session, bot_id) or 0) + 1,
        settings=body.settings,
        note=body.note,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return _version_out(version)
