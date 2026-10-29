from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, func, select

from bt_backend.agents import PROVIDERS
from bt_backend.api.schemas import BotCreate, BotDetail, BotOut, VersionCreate, VersionOut
from bt_backend.db import SessionDep
from bt_backend.models import Bot, BotVersion

router = APIRouter(prefix="/api", tags=["bots"])


def _latest_version(session: Session, bot_id: int) -> int | None:
    query = select(func.max(BotVersion.version)).where(BotVersion.bot_id == bot_id)
    return session.exec(query).one()


def _bot_out(session: Session, bot: Bot) -> BotOut:
    assert bot.id is not None
    return BotOut(**bot.model_dump(), latest_version=_latest_version(session, bot.id))


def _version_out(v: BotVersion) -> VersionOut:
    return VersionOut.model_validate(v, from_attributes=True)


@router.get("/providers")
def list_providers() -> list[str]:
    return sorted(PROVIDERS)


@router.get("/bots")
def list_bots(session: SessionDep) -> list[BotOut]:
    bots = session.exec(select(Bot).order_by(col(Bot.id))).all()
    return [_bot_out(session, b) for b in bots]


@router.post("/bots")
def create_bot(body: BotCreate, session: SessionDep) -> BotDetail:
    if body.provider not in PROVIDERS:
        raise HTTPException(400, f"未対応のプロバイダーです: {body.provider}")
    if not body.models.get("chat"):
        raise HTTPException(400, "models.chat（会話に使うモデル）を指定してください")
    bot = Bot(name=body.name, provider=body.provider, models=body.models)
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
        raise HTTPException(404, "BOT が見つかりません")
    versions = session.exec(
        select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(col(BotVersion.version))
    ).all()
    return BotDetail(
        **_bot_out(session, bot).model_dump(), versions=[_version_out(v) for v in versions]
    )


@router.post("/bots/{bot_id}/versions")
def create_version(bot_id: int, body: VersionCreate, session: SessionDep) -> VersionOut:
    if session.get(Bot, bot_id) is None:
        raise HTTPException(404, "BOT が見つかりません")
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
