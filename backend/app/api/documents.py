"""Documents routes (PDF et al.).

Author: Adaptation to TPIS.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models import Article, Project
from app.services.pdf_ingest import extract_text_smart
from app.services.pdf_projects import extract_project_names_with_claude
from app.services.pipeline import (  # noqa: PLC2701
    _normalize_project_key,
    _upsert_companies,
    _upsert_projects,
)
from app.services.llm_processing import extract_entities, classify_text

router = APIRouter()


@router.post("/documents/upload_pdf", tags=["documents"])
async def upload_pdf(
    data: bytes = Body(..., media_type="application/pdf"),
    entity_type: str = Query("article"),
    entity_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Download a PDF magazine and extract projects from it.

    :param data: Byte content of PDF file.
    :param entity_type: Type of related substance: article/project/tender/company.
    :param entity_id: Ideas Identifier (optimal).
    :param session: database session.
    :return: Information on processing and found projects.
    """

    extracted = await extract_text_smart(data)
    fragments = extracted.get("fragments") or []
    text = "\n\n".join(fragments)

    linked_to: dict[str, int | None] = {
        "project_id": None,
        "tender_id": None,
        "company_id": None,
    }
    if entity_type == "project" and entity_id:
        linked_to["project_id"] = entity_id
    if entity_type == "tender" and entity_id:
        linked_to["tender_id"] = entity_id
    if entity_type == "company" and entity_id:
        linked_to["company_id"] = entity_id

    # Save PDF as Article to participate in reports/exports.
    article = Article(
        source="pdf_upload",
        url="",
        title='PDF Log',
        text=text,
        entities=None,
        label="project",
        quality_flag=True,
    )
    session.add(article)
    await session.commit()
    await session.refresh(article)

    # Claude draws a list of projects from the text of the magazine.
    project_names = await extract_project_names_with_claude(fragments)

    # Full NLP screening via Claude: Companies, Contacts and Roles.
    entities = await extract_entities(text)
    article.entities = {
        "projects": entities.projects,
        "companies": entities.companies,
        "persons": entities.persons,
        "emails": entities.emails,
        "phones": entities.phones,
        "money": entities.money,
        "dates": entities.dates,
        "winners": entities.winners,
        "applicants": entities.applicants,
        "contractors": entities.contractors,
        "subcontractors": entities.subcontractors,
        "customers": entities.customers,
        "investors": entities.investors,
    }
    article.label = await classify_text(text)
    article.quality_flag = bool(article.title and article.text and entities.companies)
    await _upsert_companies(session, entities.companies, entities.emails, entities.phones, "pdf_upload")
    await _upsert_projects(session, entities.projects, article, text)

    created_projects: list[dict[str, Any]] = []
    combined_names = list({*project_names, *entities.projects})
    for name in combined_names:
        if not name:
            continue
        normalized_key = _normalize_project_key(name)
        existing = await session.execute(
            Project.__table__.select().where(Project.normalized_name == normalized_key)
        )
        row = existing.first()
        if row:
            continue
        project = Project(name=name, normalized_name=normalized_key)
        session.add(project)
        await session.flush()
        created_projects.append({"id": project.id, "name": project.name})

    await session.commit()

    return {
        "mode": extracted.get("mode"),
        "article_id": article.id,
        "linked_to": linked_to,
        "projects_created": created_projects,
    }

