import inspect
from collections.abc import Callable
from typing import Any


def call_with_params(create: Callable[..., Any], request: dict[str, Any]) -> Any:
    """SDK の関数を呼ぶ。SDK が引数として知らない設定は extra_body に入れて、そのまま送る。

    設定画面ではモデル以外のパラメーターをすべて変えられるため、SDK の版によって
    引数から外れたパラメーター（例: temperature）も送れるようにしておく。
    """
    accepted = set(inspect.signature(create).parameters)
    known = {k: v for k, v in request.items() if k in accepted}
    extra = {k: v for k, v in request.items() if k not in accepted}
    if extra:
        known["extra_body"] = {**known.get("extra_body", {}), **extra}
    return create(**known)
