"""シミュレータ。Agent とは独立に動き、バージョン管理はしない。

シミュレータはコードで定義する。呼ぶ側は、このファイルが公開するものだけを使う。
Agents のフォルダの外に置くので、ソースのバックアップ（スナップショット）の対象にはならない。
"""

from bt_backend.simulators.base import (
    GlobalSimulationSettings,
    InvalidArguments,
    ParamInfo,
    RawRecord,
    SimulationOutput,
    Simulator,
)
from bt_backend.simulators.chance import DiceSimulator, DiceSumSimulator, OmikujiSimulator
from bt_backend.simulators.llm import LlmSimulator

_SIMULATORS: list[Simulator] = [
    OmikujiSimulator(),
    DiceSimulator(),
    DiceSumSimulator(),
    LlmSimulator(),
]
SIMULATORS: dict[str, Simulator] = {s.name: s for s in _SIMULATORS}

__all__ = [
    "SIMULATORS",
    "GlobalSimulationSettings",
    "InvalidArguments",
    "ParamInfo",
    "RawRecord",
    "SimulationOutput",
    "Simulator",
]
