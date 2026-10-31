"""シミュレータの実行。

実行記録を通常の DB に、各回の LLM 呼び出しをシミュレート用の RAW に保存する。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlmodel import Session

from bt_backend.agents import SimulationCall, SimulatorAccess, SimulatorTool
from bt_backend.models import SimulationRun, SimulationSettingsRow, utcnow
from bt_backend.raw_models import SimulationRawCall
from bt_backend.simulators import SIMULATORS, GlobalSimulationSettings, InvalidArguments

SETTINGS_ROW_ID = 1


@dataclass
class Caller:
    """シミュレータの呼び出し元。"""

    kind: Literal["conversation", "dialogue", "webui", "parallel"]
    agent_id: str = ""
    conversation_id: int | None = None
    dialogue_id: int | None = None
    parallel_candidate_id: int | None = None
    # このターンで記録した実行の id（ターンの発言を保存した後に、発言と結びつける）
    run_ids: list[int] = field(default_factory=list)


def global_settings(session: Session) -> GlobalSimulationSettings:
    row = session.get(SimulationSettingsRow, SETTINGS_ROW_ID)
    return GlobalSimulationSettings.model_validate(row.values if row else {})


def save_global_settings(session: Session, settings: GlobalSimulationSettings) -> None:
    row = session.get(SimulationSettingsRow, SETTINGS_ROW_ID) or SimulationSettingsRow(
        id=SETTINGS_ROW_ID, values={}
    )
    row.values = settings.model_dump()
    row.updated_at = utcnow()
    session.add(row)
    session.commit()


def simulate(
    session: Session,
    raw_session: Session,
    name: str,
    args: dict[str, Any],
    caller: Caller,
    api_keys: Mapping[str, str | None],
) -> SimulationCall:
    """シミュレータを 1 回実行し、記録する。失敗しても例外は投げず、結果に入れる。

    引数が足りない・合わないときは実行せず、呼ぶ側が判断できる結果（ok と missing）を返す。
    """
    simulator = SIMULATORS.get(name)
    if simulator is None:
        return SimulationCall(
            run_id=None,
            ok=False,
            result={"ok": False, "error": f"シミュレータがありません: {name}"},
        )
    run = SimulationRun(
        simulator=name,
        caller=caller.kind,
        conversation_id=caller.conversation_id,
        dialogue_id=caller.dialogue_id,
        parallel_candidate_id=caller.parallel_candidate_id,
        agent_id=caller.agent_id,
        args=args,
        status="invalid",
    )
    raw: list[Any] = []
    try:
        params = simulator.resolve(args, global_settings(session))
    except InvalidArguments as e:
        run.error = str(e)
        reply: dict[str, Any] = {"ok": False, "error": str(e), "missing": e.missing}
    else:
        run.params = params
        output = simulator.run(params, api_keys)
        run.status = output.status
        run.result = output.result
        run.detail = output.detail
        run.error_count = output.error_count
        run.error = output.error
        raw = output.raw
        if output.status == "succeeded":
            reply = {"ok": True, "result": output.result}
        else:
            reply = {"ok": False, "error": output.error}
        if params.get("runs") is not None:
            reply["error_count"] = output.error_count
    run.finished_at = utcnow()
    session.add(run)
    session.commit()
    assert run.id is not None
    caller.run_ids.append(run.id)
    for r in raw:
        raw_session.add(
            SimulationRawCall(
                simulator=name,
                simulation_run_id=run.id,
                label=r.label,
                exchanges=r.exchanges,
                error=r.error,
            )
        )
    raw_session.commit()
    return SimulationCall(run_id=run.id, ok=reply["ok"], result=reply)


def access_for(
    session: Session, raw_session: Session, caller: Caller, api_keys: Mapping[str, str | None]
) -> SimulatorAccess:
    """1 ターンの間に Agent が使うシミュレータ。呼ぶと caller の名で記録する。"""
    tools = [SimulatorTool(s.name, s.description, s.input_schema()) for s in SIMULATORS.values()]

    def call(name: str, args: dict[str, Any]) -> SimulationCall:
        return simulate(session, raw_session, name, args, caller, api_keys)

    return SimulatorAccess(tools=tools, call=call)


def link_runs(
    session: Session,
    caller: Caller,
    message_id: int | None = None,
    dialogue_message_id: int | None = None,
) -> None:
    """このターンの実行記録を、ターンの発言に結びつける。"""
    for run_id in caller.run_ids:
        run = session.get(SimulationRun, run_id)
        assert run is not None
        run.message_id = message_id
        run.dialogue_message_id = dialogue_message_id
        session.add(run)
    session.commit()
