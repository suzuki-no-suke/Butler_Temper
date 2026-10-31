"""Agent テンプレート（Agent 設定に埋め込む文章）。名前は変えられず、中身はバージョンとして積む。

対話用テンプレート（api/templates.py）とは表も API も分ける。
"""

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, func, select

from bt_backend.agent_templates import latest_agent_template_version
from bt_backend.api.schemas import (
    AgentTemplateUsedOut,
    TemplateCreate,
    TemplateDetail,
    TemplateOut,
    TemplateVersionCreate,
    TemplateVersionOut,
)
from bt_backend.db import SessionDep
from bt_backend.dialogues import sanitize_template
from bt_backend.models import AgentTemplate, AgentTemplateVersion

router = APIRouter(prefix="/api", tags=["agent-templates"])


def _out(session: Session, t: AgentTemplate) -> TemplateOut:
    assert t.id is not None
    return TemplateOut(
        **t.model_dump(), latest_version=latest_agent_template_version(session, t.id).version
    )


def used_agent_templates(
    session: Session, version_ids: dict[str, int] | None
) -> list[AgentTemplateUsedOut]:
    """会話などに固定した Agent テンプレートのバージョンと本文。"""
    out: list[AgentTemplateUsedOut] = []
    for name, version_id in (version_ids or {}).items():
        version = session.get(AgentTemplateVersion, version_id)
        assert version is not None
        out.append(
            AgentTemplateUsedOut(
                name=name,
                template_id=version.template_id,
                version=version.version,
                content=version.content,
            )
        )
    return out


@router.get("/agent-templates")
def list_agent_templates(session: SessionDep) -> list[TemplateOut]:
    query = select(AgentTemplate).order_by(col(AgentTemplate.id))
    return [_out(session, t) for t in session.exec(query)]


@router.post("/agent-templates")
def create_agent_template(body: TemplateCreate, session: SessionDep) -> TemplateDetail:
    name = body.name.strip()
    if session.exec(select(AgentTemplate).where(AgentTemplate.name == name)).first() is not None:
        raise HTTPException(409, f"同じ名前の Agent テンプレートがあります: {name}")
    template = AgentTemplate(name=name)
    session.add(template)
    session.flush()
    assert template.id is not None
    session.add(
        AgentTemplateVersion(
            template_id=template.id,
            version=1,
            content=sanitize_template(body.content),
            note=body.note,
        )
    )
    session.commit()
    return get_agent_template(template.id, session)


@router.get("/agent-templates/{template_id}")
def get_agent_template(template_id: int, session: SessionDep) -> TemplateDetail:
    template = session.get(AgentTemplate, template_id)
    if template is None:
        raise HTTPException(404, "Agent テンプレートが見つかりません")
    versions = session.exec(
        select(AgentTemplateVersion)
        .where(AgentTemplateVersion.template_id == template_id)
        .order_by(col(AgentTemplateVersion.version))
    )
    return TemplateDetail(
        **_out(session, template).model_dump(),
        versions=[TemplateVersionOut.model_validate(v, from_attributes=True) for v in versions],
    )


@router.post("/agent-templates/{template_id}/versions")
def create_agent_template_version(
    template_id: int, body: TemplateVersionCreate, session: SessionDep
) -> TemplateVersionOut:
    if session.get(AgentTemplate, template_id) is None:
        raise HTTPException(404, "Agent テンプレートが見つかりません")
    query = select(func.max(AgentTemplateVersion.version)).where(
        AgentTemplateVersion.template_id == template_id
    )
    version = AgentTemplateVersion(
        template_id=template_id,
        version=(session.exec(query).one() or 0) + 1,
        content=sanitize_template(body.content),
        note=body.note,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return TemplateVersionOut.model_validate(version, from_attributes=True)
