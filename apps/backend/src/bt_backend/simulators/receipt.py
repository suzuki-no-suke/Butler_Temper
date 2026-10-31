"""レシートを出すシミュレータ。本システムでは、印刷の代わりに表の形の文を返して終わる。

別のシステムでは、同じ引数で本当に紙に印刷する想定。何を印字するかは呼ぶ側が決める。
運勢と合計額だけは、呼ぶ側に決めさせずにシミュレータが出す。
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bt_backend.simulators import chance
from bt_backend.simulators.base import SimulationOutput, Simulator, SimulatorArgs


class ReceiptField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str


class ReceiptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    price: int = Field(ge=0, description="金額（円）")


class ReceiptArgs(SimulatorArgs):
    kind: str = Field(description="レシートの種類（おみくじ模倣・レシート模倣など）")
    title: str = Field(default="", description="レシートの見出し")
    fields: list[ReceiptField] = Field(default_factory=list, description="印字する項目と中身")
    items: list[ReceiptItem] | None = Field(
        default=None, description="品物と金額。渡すと合計額をシミュレータが計算して印字する"
    )
    fortune: bool = Field(default=False, description="true なら運勢をシミュレータが引いて印字する")
    footer: list[str] = Field(default_factory=list, description="末尾に印字する付随情報")


def _render(params: dict[str, Any], fortune: str | None, total: int | None) -> str:
    lines = [f"==== {params['title'] or params['kind']} ====", f"種類: {params['kind']}"]
    if fortune is not None:
        lines.append(f"運勢: {fortune}")
    if params["fields"]:
        lines += ["", "| 項目 | 内容 |", "| --- | --- |"]
        lines += [f"| {f['label']} | {f['value']} |" for f in params["fields"]]
    if params["items"] is not None:
        lines += ["", "| 品物 | 金額 |", "| --- | --- |"]
        lines += [f"| {i['name']} | {i['price']}円 |" for i in params["items"]]
        lines.append(f"| 合計 | {total}円 |")
    if params["footer"]:
        lines += ["", "----", *params["footer"]]
    return "\n".join(lines)


class ReceiptSimulator(Simulator):
    name = "receipt"
    label = "レシート"
    description = "レシートを 1 枚出す（本システムでは印刷の代わりに表の形の文を返す）。"
    result_description = (
        '{"kind": 種類, "printed": 印字した文, "fortune": 運勢（fortune のとき）,'
        ' "total": 合計額（items のとき）}'
    )
    args_model = ReceiptArgs

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        fortune: str | None = None
        if params["fortune"]:
            [fortune] = chance.rng.choices(
                list(chance.FORTUNES), weights=list(chance.FORTUNES.values())
            )
        total = sum(i["price"] for i in params["items"]) if params["items"] is not None else None
        result: dict[str, Any] = {
            "kind": params["kind"],
            "printed": _render(params, fortune, total),
        }
        if fortune is not None:
            result["fortune"] = fortune
        if total is not None:
            result["total"] = total
        return SimulationOutput(status="succeeded", result=result)
