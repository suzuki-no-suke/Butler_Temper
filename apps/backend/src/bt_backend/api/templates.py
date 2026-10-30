"""テンプレート（プロンプトに埋め込む文章）。名前は変えられず、中身はバージョンとして積む。"""

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, func, select

from bt_backend.api.schemas import (
    TemplateCreate,
    TemplateDetail,
    TemplateOut,
    TemplateVersionCreate,
    TemplateVersionOut,
)
from bt_backend.db import SessionDep
from bt_backend.dialogues import sanitize_template
from bt_backend.models import Template, TemplateVersion

router = APIRouter(prefix="/api", tags=["templates"])


def latest_template_version(session: Session, template_id: int) -> TemplateVersion:
    version = session.exec(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(col(TemplateVersion.version).desc())
    ).first()
    assert version is not None
    return version


def _out(session: Session, t: Template) -> TemplateOut:
    assert t.id is not None
    return TemplateOut(
        **t.model_dump(), latest_version=latest_template_version(session, t.id).version
    )


@router.get("/templates")
def list_templates(session: SessionDep) -> list[TemplateOut]:
    return [_out(session, t) for t in session.exec(select(Template).order_by(col(Template.id)))]


@router.post("/templates")
def create_template(body: TemplateCreate, session: SessionDep) -> TemplateDetail:
    name = body.name.strip()
    if session.exec(select(Template).where(Template.name == name)).first() is not None:
        raise HTTPException(409, f"同じ名前のテンプレートがあります: {name}")
    template = Template(name=name)
    session.add(template)
    session.flush()
    assert template.id is not None
    session.add(
        TemplateVersion(
            template_id=template.id,
            version=1,
            content=sanitize_template(body.content),
            note=body.note,
        )
    )
    session.commit()
    return get_template(template.id, session)


@router.get("/templates/{template_id}")
def get_template(template_id: int, session: SessionDep) -> TemplateDetail:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(404, "テンプレートが見つかりません")
    versions = session.exec(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(col(TemplateVersion.version))
    )
    return TemplateDetail(
        **_out(session, template).model_dump(),
        versions=[TemplateVersionOut.model_validate(v, from_attributes=True) for v in versions],
    )


@router.post("/templates/{template_id}/versions")
def create_template_version(
    template_id: int, body: TemplateVersionCreate, session: SessionDep
) -> TemplateVersionOut:
    if session.get(Template, template_id) is None:
        raise HTTPException(404, "テンプレートが見つかりません")
    query = select(func.max(TemplateVersion.version)).where(
        TemplateVersion.template_id == template_id
    )
    version = TemplateVersion(
        template_id=template_id,
        version=(session.exec(query).one() or 0) + 1,
        content=sanitize_template(body.content),
        note=body.note,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return TemplateVersionOut.model_validate(version, from_attributes=True)
