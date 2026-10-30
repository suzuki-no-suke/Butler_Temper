"""シミュレータの型と、全体の設定（グローバル設定）。

シミュレータは、呼ばれたときの引数を受けて結果を返すだけのもの。Agent とは独立していて、
バージョン管理はしない。いつ呼ぶかは呼ぶ側（Agent）が決める。
引数が揃っているかどうかだけはシミュレータが判断し、判断できる形の結果を返す。

項目（パラメーター）は次の三つに分ける。実行のたびに、実際に使った値をすべて保存する。
- 必須（required）: 呼ぶ側が必ず渡す
- 任意（optional）: 呼ぶ側が渡さなければ、グローバル設定などの既定の値を使う
- 指定不可（global）: グローバル設定でのみ決める。呼ぶ側は渡せない
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ParamKind = Literal["required", "optional", "global"]

DEFAULT_MERGE_INSTRUCTION = """\
次の「条件」で、同じシミュレートを別々に何回か行いました。その結果をすべて読み、
全体としての結果を、submit_result の形式で提出してください。
回ごとのばらつきや食い違いも、全体の結果として扱ってください。"""


class GlobalSimulationSettings(BaseModel):
    """シミュレータの全体の設定。画面から変える。バージョン管理はしない。"""

    model_config = ConfigDict(extra="forbid")

    llm_runs: int = Field(
        default=20, ge=1, le=100, description="LLM シミュレータ: 同じプロンプトで別々に呼ぶ回数"
    )
    llm_model: str = Field(
        default="claude-sonnet-5-5", description="LLM シミュレータ: 各回のモデル"
    )
    llm_merge_model: str = Field(
        default="claude-sonnet-5-5", description="LLM シミュレータ: 全体の結果をまとめる回のモデル"
    )
    llm_merge_instruction: str = Field(
        default=DEFAULT_MERGE_INSTRUCTION,
        description="LLM シミュレータ: まとめる回への指示。条件と各回の出力の前に置く",
    )
    llm_run_max_tokens: int = Field(
        default=2048, ge=1, description="LLM シミュレータ: 各回の出力の上限（max_tokens）"
    )
    llm_merge_max_tokens: int = Field(
        default=4096, ge=1, description="LLM シミュレータ: まとめる回の出力の上限（max_tokens）"
    )
    llm_concurrency: int = Field(
        default=5, ge=1, le=20, description="LLM シミュレータ: 各回を同時に呼ぶ数"
    )


@dataclass(frozen=True)
class ParamInfo:
    name: str
    kind: ParamKind
    description: str
    # 任意・指定不可の項目が、既定の値を取るグローバル設定の項目名
    global_key: str | None = None


@dataclass
class RawRecord:
    """シミュレート用の RAW に残す、1 回分の LLM 呼び出し。"""

    # シミュレータ内での呼び出しの役割（run-1 / merge など）
    label: str
    exchanges: list[dict[str, Any]]
    error: str | None = None


@dataclass
class SimulationOutput:
    status: Literal["succeeded", "failed"]
    # 呼ぶ側に返す結果。形式はシミュレータが決める
    result: dict[str, Any] | None = None
    error: str | None = None
    # LLM 呼び出しのエラーの回数
    error_count: int = 0
    # 結果のほかに記録しておく内訳（各回の出目、各回の出力など）
    detail: dict[str, Any] | None = None
    raw: list[RawRecord] = field(default_factory=list)


class InvalidArguments(Exception):
    def __init__(self, message: str, missing: list[str]) -> None:
        super().__init__(message)
        self.missing = missing


class SimulatorArgs(BaseModel):
    """呼ぶ側が渡す引数。知らない項目（指定不可の項目を含む）はエラーにする。"""

    model_config = ConfigDict(extra="forbid")


class Simulator(ABC):
    name: str
    label: str
    # Agent の LLM に見せる短い固定の説明。いつ使うかは Agent 側に書く
    description: str
    # 結果の形式の説明（画面に出す）
    result_description: str
    args_model: type[SimulatorArgs]
    # 任意の項目のうち、渡されなければグローバル設定の値を使うもの（引数名 -> 設定の項目名）
    global_defaults: Mapping[str, str] = {}
    # 指定不可の項目（グローバル設定の項目名）
    global_only: tuple[str, ...] = ()

    def input_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return schema

    def params(self) -> list[ParamInfo]:
        out: list[ParamInfo] = []
        for name, f in self.args_model.model_fields.items():
            out.append(
                ParamInfo(
                    name=name,
                    kind="required" if f.is_required() else "optional",
                    description=f.description or "",
                    global_key=self.global_defaults.get(name),
                )
            )
        for key in self.global_only:
            description = GlobalSimulationSettings.model_fields[key].description or ""
            out.append(ParamInfo(name=key, kind="global", description=description, global_key=key))
        return out

    def resolve(self, args: dict[str, Any], settings: GlobalSimulationSettings) -> dict[str, Any]:
        """実行に使う値をすべて決める。引数が足りない・合わないときは InvalidArguments。"""
        try:
            parsed = self.args_model.model_validate(args)
        except ValidationError as e:
            missing = [str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"]
            raise InvalidArguments(str(e), missing) from e
        params = parsed.model_dump(mode="json")
        values = settings.model_dump()
        for name, key in self.global_defaults.items():
            if params.get(name) is None:
                params[name] = values[key]
        for key in self.global_only:
            params[key] = values[key]
        self.check(params)
        return params

    def check(self, params: dict[str, Any]) -> None:
        """型だけでは確かめられない引数の決まり。合わなければ InvalidArguments を投げる。"""
        return None

    @abstractmethod
    def run(
        self, params: dict[str, Any], api_keys: Mapping[str, str | None]
    ) -> SimulationOutput: ...
