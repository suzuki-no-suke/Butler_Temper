"""Agent テンプレート。Agent 設定の文字列の中の {{agent_template:名前}} を、本文に置き換える。

会話・エージェント間対話・並行会話を始めたときに、その時点の最新のバージョンで置き換えた設定と、
使ったバージョンを記録して固定する。以後のターンは固定した設定で動く。
- 置き換えは、設定の中の文字列の値ごとに行う。JSON の文字列として埋め込むのではないので、
  本文の改行や引用符をエスケープする必要は無い
- 置き換えは一度だけ行い、埋め込んだ本文の中の {{agent_template:...}} はそのまま残す
  （入れ子にしない）
- 対話用テンプレート（{{template:名前}}）とは書き方も表も分け、混ぜない
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, col, select

from bt_backend.models import AgentTemplate, AgentTemplateVersion

PLACEHOLDER = re.compile(r"\{\{agent_template:([^{}\n]+?)\}\}")


class MissingAgentTemplate(Exception):
    def __init__(self, names: list[str]) -> None:
        super().__init__(f"Agent 設定にある Agent テンプレートが見つかりません: {', '.join(names)}")
        self.names = names


@dataclass
class ResolvedSettings:
    settings: dict[str, Any]
    # 名前 -> AgentTemplateVersion.id
    version_ids: dict[str, int]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def referenced_agent_templates(settings: Any) -> list[str]:
    """設定の中の文字列すべてから、参照している Agent テンプレートの名前を出てきた順に返す。"""
    names: list[str] = []
    for text in _strings(settings):
        for match in PLACEHOLDER.finditer(text):
            name = match.group(1).strip()
            if name not in names:
                names.append(name)
    return names


def expand_agent_templates(value: Any, contents: dict[str, str]) -> Any:
    """設定の中の文字列すべてで、{{agent_template:名前}} を本文に置き換えたものを返す。"""
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: contents[m.group(1).strip()], value)
    if isinstance(value, dict):
        return {k: expand_agent_templates(v, contents) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_agent_templates(v, contents) for v in value]
    return value


def latest_agent_template_version(session: Session, template_id: int) -> AgentTemplateVersion:
    version = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.template_id == template_id)
        .order_by(col(AgentTemplateVersion.version).desc())
    ).first()
    assert version is not None
    return version


def resolve_agent_settings(session: Session, settings: dict[str, Any]) -> ResolvedSettings:
    """今の最新のバージョンで置き換える。見つからないテンプレートがあれば MissingAgentTemplate。"""
    contents: dict[str, str] = {}
    version_ids: dict[str, int] = {}
    missing: list[str] = []
    for name in referenced_agent_templates(settings):
        template = session.exec(select(AgentTemplate).where(AgentTemplate.name == name)).first()
        if template is None or template.id is None:
            missing.append(name)
            continue
        latest = latest_agent_template_version(session, template.id)
        assert latest.id is not None
        contents[name] = latest.content
        version_ids[name] = latest.id
    if missing:
        raise MissingAgentTemplate(missing)
    return ResolvedSettings(expand_agent_templates(settings, contents), version_ids)


def run_settings(
    resolved: dict[str, Any] | None, version_settings: dict[str, Any]
) -> dict[str, Any]:
    """ターンを動かすときの Agent 設定。

    固定した設定が無い（Agent テンプレートの仕組みより前の）記録では、バージョンの設定を使う。
    """
    return resolved if resolved is not None else version_settings
