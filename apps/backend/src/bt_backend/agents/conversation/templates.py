"""テンプレートの埋め込み。

プロンプト中の {{template:名前}} を、そのテンプレートの本文に置き換える。
置き換えは一度だけ行い、埋め込んだ本文の中の {{template:...}} はそのまま残す（入れ子にしない）。
"""

import re
from collections.abc import Iterator, Mapping
from typing import Any

PLACEHOLDER = re.compile(r"\{\{template:([^{}\n]+?)\}\}")


class MissingTemplate(Exception):
    pass


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def referenced_templates(settings: Any) -> list[str]:
    """設定の中の文字列すべてから、埋め込まれているテンプレートの名前を出てきた順に返す。"""
    names: list[str] = []
    for text in _strings(settings):
        for match in PLACEHOLDER.finditer(text):
            name = match.group(1).strip()
            if name not in names:
                names.append(name)
    return names


def expand_templates(text: str, templates: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name not in templates:
            raise MissingTemplate(f"テンプレートが見つかりません: {name}")
        return templates[name]

    return PLACEHOLDER.sub(replace, text)
