"""LLM シミュレータ。同じプロンプトで別々に何回か LLM を呼び、最後の 1 回で全体の結果にまとめる。

1. 呼ぶ側が、プロンプト（シミュレートの条件）と、結果の形式（JSON Schema）を渡す
2. 同じプロンプトで、別々に runs 回 LLM を呼ぶ（会話の文脈は持たせない）
3. 最後の 1 回で、条件と各回の出力をすべてコンテキストに入れ、tool use で結果の形式にまとめる

LLM 呼び出しのエラーは、その回だけをやり直さずに打ち切り、エラーとして数える。
すべての回が失敗したとき（またはまとめる回が失敗したとき）だけ、全体を失敗とする。
"""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import Field

from bt_backend.agents import LlmSession, anthropic_text
from bt_backend.simulators.base import (
    InvalidArguments,
    RawRecord,
    SimulationOutput,
    Simulator,
    SimulatorArgs,
)

RESULT_TOOL = "submit_result"

DEFAULT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"result": {"type": "string", "description": "全体としての結果"}},
    "required": ["result"],
}


class LlmArgs(SimulatorArgs):
    prompt: str = Field(min_length=1, description="シミュレートの条件。各回にそのまま送る")
    runs: int | None = Field(
        default=None, ge=1, le=100, description="別々に呼ぶ回数（既定はグローバル設定）"
    )
    model: str | None = Field(default=None, description="各回のモデル（既定はグローバル設定）")
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description=(
            '全体の結果の形式（type が object の JSON Schema）。既定は {"result": 文章} の形'
        ),
    )


def _error(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


class LlmSimulator(Simulator):
    name = "llm"
    label = "LLM シミュレータ"
    description = (
        "プロンプトの条件で LLM に何回か別々にシミュレートさせ、"
        "全体の結果を output_schema の形で返す。"
    )
    result_description = 'output_schema の形（既定は {"result": 文章}）'
    args_model = LlmArgs
    global_defaults = {"runs": "llm_runs", "model": "llm_model"}
    global_only = (
        "llm_merge_model",
        "llm_merge_instruction",
        "llm_run_max_tokens",
        "llm_merge_max_tokens",
        "llm_concurrency",
    )

    def check(self, params: dict[str, Any]) -> None:
        if params["output_schema"] is None:
            params["output_schema"] = DEFAULT_OUTPUT_SCHEMA
        elif params["output_schema"].get("type") != "object":
            raise InvalidArguments(
                "output_schema は type が object の JSON Schema にしてください", []
            )

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        def one(i: int) -> tuple[str | None, RawRecord]:
            llm = LlmSession(api_keys)
            label = f"run-{i + 1}"
            try:
                message = llm.anthropic(
                    label,
                    {
                        "model": params["model"],
                        "max_tokens": params["llm_run_max_tokens"],
                        "messages": [{"role": "user", "content": params["prompt"]}],
                    },
                )
                return anthropic_text(message), RawRecord(label, llm.exchanges)
            except Exception as e:  # noqa: BLE001 - その回だけ打ち切って数える
                return None, RawRecord(label, llm.exchanges, _error(e))

        with ThreadPoolExecutor(max_workers=params["llm_concurrency"]) as pool:
            done = list(pool.map(one, range(params["runs"])))
        raw = [r for _, r in done]
        outputs = [
            {"run": i + 1, "text": text, "error": r.error} for i, (text, r) in enumerate(done)
        ]
        errors = [r.error for r in raw if r.error is not None]
        detail: dict[str, Any] = {"outputs": outputs}
        if len(errors) == len(done):
            return SimulationOutput(
                status="failed",
                error=f"{len(done)} 回すべて失敗しました（最初のエラー: {errors[0]}）",
                error_count=len(errors),
                detail=detail,
                raw=raw,
            )

        results = "\n\n".join(
            f"## {o['run']} 回目\n{o['text']}" for o in outputs if o["error"] is None
        )
        content = (
            f"{params['llm_merge_instruction']}\n\n# 条件\n{params['prompt']}\n\n# 各回の結果\n"
            f"{results}"
        )
        llm = LlmSession(api_keys)
        try:
            message = llm.anthropic(
                "merge",
                {
                    "model": params["llm_merge_model"],
                    "max_tokens": params["llm_merge_max_tokens"],
                    "messages": [{"role": "user", "content": content}],
                    "tools": [
                        {
                            "name": RESULT_TOOL,
                            "description": "全体としての結果を提出する",
                            "input_schema": params["output_schema"],
                        }
                    ],
                    "tool_choice": {"type": "tool", "name": RESULT_TOOL},
                },
            )
            use = next((b for b in message.content if b.type == "tool_use"), None)
            if use is None:
                raise ValueError("まとめる回が結果を提出しませんでした")
        except Exception as e:  # noqa: BLE001 - 失敗として記録する
            raw.append(RawRecord("merge", llm.exchanges, _error(e)))
            return SimulationOutput(
                status="failed",
                error=f"まとめる回が失敗しました: {_error(e)}",
                error_count=len(errors) + 1,
                detail=detail,
                raw=raw,
            )
        raw.append(RawRecord("merge", llm.exchanges))
        return SimulationOutput(
            status="succeeded",
            result=dict(use.input),
            error_count=len(errors),
            detail=detail,
            raw=raw,
        )
