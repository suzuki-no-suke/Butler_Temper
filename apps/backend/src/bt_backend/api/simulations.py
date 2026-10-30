"""シミュレータ。一覧・テスト実行・実行記録・グローバル設定。"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from sqlmodel import col, select

from bt_backend.api.schemas import (
    SimulationRawCallOut,
    SimulationRunDetail,
    SimulationRunOut,
    SimulationSettingsOut,
    SimulationTestRun,
    SimulatorOut,
    SimulatorParamOut,
    SimulatorProposeIn,
    SimulatorProposeOut,
)
from bt_backend.config import get_settings as get_app_settings
from bt_backend.db import RawSessionDep, SessionDep
from bt_backend.models import SimulationRun
from bt_backend.raw_models import SimulationRawCall
from bt_backend.services import api_keys
from bt_backend.simulations import Caller, global_settings, save_global_settings, simulate
from bt_backend.simulators import SIMULATORS, GlobalSimulationSettings
from bt_backend.simulators.propose import ChatLine, propose_args

router = APIRouter(prefix="/api", tags=["simulations"])


@router.get("/simulators")
def list_simulators(session: SessionDep) -> list[SimulatorOut]:
    settings = global_settings(session)
    out: list[SimulatorOut] = []
    for s in SIMULATORS.values():
        defaults = s.defaults(settings)
        out.append(
            SimulatorOut(
                name=s.name,
                label=s.label,
                description=s.description,
                result_description=s.result_description,
                input_schema=s.input_schema(),
                params=[
                    SimulatorParamOut(**vars(p), default=defaults.get(p.name)) for p in s.params()
                ],
            )
        )
    return out


@router.post("/simulators/{name}/propose")
def propose(name: str, body: SimulatorProposeIn, session: SessionDep) -> SimulatorProposeOut:
    """要望から、シミュレータにそのまま渡せる引数を提案する（保存はしない）。"""
    simulator = SIMULATORS.get(name)
    if simulator is None:
        raise HTTPException(404, f"シミュレータがありません: {name}")
    try:
        proposal = propose_args(
            simulator,
            global_settings(session),
            body.current_args,
            [
                ChatLine(role=h.get("role", "user"), content=h.get("content", ""))
                for h in body.history
            ],
            body.request,
            get_app_settings().anthropic_api_key,
        )
    except Exception as e:  # noqa: BLE001 - 失敗の内容を画面に返す
        raise HTTPException(502, f"引数の提案に失敗しました: {type(e).__name__}: {e}") from e
    return SimulatorProposeOut(reply=proposal.reply, args=proposal.args)


@router.post("/simulators/{name}/runs")
def test_run(
    name: str, body: SimulationTestRun, session: SessionDep, raw_session: RawSessionDep
) -> list[SimulationRunOut]:
    """画面からのテスト実行。times 回続けて実行し、呼び出し元を webui として記録する。"""
    if name not in SIMULATORS:
        raise HTTPException(404, f"シミュレータがありません: {name}")
    out: list[SimulationRunOut] = []
    for _ in range(body.times):
        call = simulate(session, raw_session, name, body.args, Caller(kind="webui"), api_keys())
        run = session.get(SimulationRun, call.run_id)
        assert run is not None
        out.append(SimulationRunOut(**run.model_dump()))
    return out


@router.get("/simulation-runs")
def list_runs(
    session: SessionDep,
    simulator: str | None = None,
    caller: str | None = None,
    limit: int = 200,
) -> list[SimulationRunOut]:
    query = select(SimulationRun).order_by(col(SimulationRun.id).desc()).limit(limit)
    if simulator:
        query = query.where(SimulationRun.simulator == simulator)
    if caller:
        query = query.where(SimulationRun.caller == caller)
    return [SimulationRunOut(**r.model_dump()) for r in session.exec(query)]


@router.get("/simulation-runs/{run_id}")
def get_run(run_id: int, session: SessionDep, raw_session: RawSessionDep) -> SimulationRunDetail:
    run = session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "実行記録が見つかりません")
    raws = raw_session.exec(
        select(SimulationRawCall)
        .where(SimulationRawCall.simulation_run_id == run_id)
        .order_by(col(SimulationRawCall.id))
    )
    return SimulationRunDetail(
        **run.model_dump(),
        raw_calls=[SimulationRawCallOut(**r.model_dump()) for r in raws],
    )


def _settings_out(settings: GlobalSimulationSettings) -> SimulationSettingsOut:
    return SimulationSettingsOut(
        values=settings.model_dump(),
        defaults=GlobalSimulationSettings().model_dump(),
        descriptions={
            k: f.description or "" for k, f in GlobalSimulationSettings.model_fields.items()
        },
    )


@router.get("/simulation-settings")
def get_settings(session: SessionDep) -> SimulationSettingsOut:
    return _settings_out(global_settings(session))


@router.put("/simulation-settings")
def put_settings(values: dict[str, Any], session: SessionDep) -> SimulationSettingsOut:
    try:
        settings = GlobalSimulationSettings.model_validate(values)
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e
    save_global_settings(session, settings)
    return _settings_out(settings)
