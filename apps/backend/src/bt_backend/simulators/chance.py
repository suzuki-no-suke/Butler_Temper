"""普通の乱数で動くシミュレータ（サイコロ・おみくじ）。LLM は使わない。"""

import random
from collections.abc import Mapping
from typing import Any

from pydantic import Field

from bt_backend.simulators.base import SimulationOutput, Simulator, SimulatorArgs

# テストで差し替えるためのもの
rng = random.Random()


class DiceArgs(SimulatorArgs):
    m: int = Field(ge=1, le=1_000_000, description="出目の最大（1 から m までの目が出る）")


class DiceSumArgs(SimulatorArgs):
    n: int = Field(ge=1, le=1000, description="振るサイコロの数")
    m: int = Field(ge=1, le=1_000_000, description="出目の最大（1 から m までの目が出る）")


class DiceSimulator(Simulator):
    name = "dice"
    label = "サイコロ（1 個）"
    description = "出目の最大が m のサイコロを 1 回振り、出目を返す。"
    result_description = '{"value": 出目}'
    args_model = DiceArgs

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        return SimulationOutput(status="succeeded", result={"value": rng.randint(1, params["m"])})


class DiceSumSimulator(Simulator):
    name = "dice_sum"
    label = "サイコロ（n 個の合計）"
    description = "出目の最大が m のサイコロを n 回振り、出目の合計を返す。"
    result_description = '{"total": 出目の合計}（各回の出目は実行記録に残す）'
    args_model = DiceSumArgs

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        rolls = [rng.randint(1, params["m"]) for _ in range(params["n"])]
        return SimulationOutput(
            status="succeeded", result={"total": sum(rolls)}, detail={"rolls": rolls}
        )


# 吉凶と、その割合
FORTUNES: dict[str, int] = {"大吉": 5, "中吉": 20, "吉": 50, "凶": 20, "大凶": 5}


class OmikujiSimulator(Simulator):
    name = "omikuji"
    label = "おみくじ"
    description = "おみくじを 1 回引き、吉凶を返す。"
    result_description = '{"fortune": 吉凶}（大吉 5・中吉 20・吉 50・凶 20・大凶 5 の割合）'
    args_model = SimulatorArgs

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        [fortune] = rng.choices(list(FORTUNES), weights=list(FORTUNES.values()))
        return SimulationOutput(status="succeeded", result={"fortune": fortune})
