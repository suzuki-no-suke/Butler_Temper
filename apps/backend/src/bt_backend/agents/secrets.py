"""秘密開示系の Agent が共通で使う、秘密と開示条件の組の扱い。"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class SecretBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 秘密を見分ける名前。Agent の状態（開示済みの一覧）にもこの名前で残る
    name: str
    secret: str
    condition: str


def check_unique_names(secrets: list[Any]) -> None:
    names = [s.name for s in secrets]
    if len(names) != len(set(names)):
        raise ValueError("secrets の name が重複しています")


def lift_single_secret(data: Any, extra_keys: tuple[str, ...] = ()) -> Any:
    """秘密が一つだけだった頃の設定（secret / condition）を secrets の形に直す。

    保存済みの古いバージョンの設定を、そのまま使えるようにするため。
    """
    if not isinstance(data, dict) or ("secret" not in data and "condition" not in data):
        return data
    data = dict(data)
    item = {"name": "secret"}
    for key in ("secret", "condition", *extra_keys):
        if key in data:
            item[key] = data.pop(key)
    data["secrets"] = [item]
    return data


def disclosed_names(state: dict[str, Any], secret_names: list[str]) -> list[str]:
    """状態に残っている開示済みの秘密の名前。古い形（true / false）も読む。"""
    disclosed = state.get("disclosed")
    if disclosed is True:
        return list(secret_names[:1])
    if isinstance(disclosed, list):
        return [str(n) for n in disclosed]
    return []
