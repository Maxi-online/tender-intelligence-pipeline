"""API routes for basic entities.

Author: Maxi-online
"""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, nulls_last, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models import Article, Company, MatchLink, Project, Source, Tender
from app.schemas import (
    ArticleCreate,
    ArticleRead,
    CompanyCreate,
    CompanyRead,
    MatchLinkCreate,
    MatchLinkRead,
    ProjectCreate,
    ProjectRead,
    SourceCreate,
    SourceRead,
    TextRequestCreate,
    TenderCreate,
    TenderRead,
    SearchKeywordSetCreate,
    SearchKeywordSetRead,
    SearchKeywordSetUpdate,
)
from app.services.config_loader import load_keywords_config, load_sources_config
from app.services.dedupe_companies import dedupe_companies
from app.services.discovery import DiscoveryService
from app.services.exporter import (
    export_dossier_docx,
    export_dossier_pdf,
    export_projects_excel_template,
    export_records,
)
from app.services.automation_state import get_state, set_enabled
from app.services.search_settings import get_search_settings, update_search_settings
from app.services.matching import diff_fields
from app.services.llm_processing import classify_text, extract_entities
from app.services.pipeline import ingest_sources, match_tenders_and_articles
from app.services.seldon_client import SeldonClient
from app.services.seldon_service import fetch_tenders, ingest_tenders
from app.services.keywords import (
    bootstrap_keyword_sets_from_yaml,
    create_keyword_set,
    delete_keyword_set,
    list_keyword_sets,
    resolve_keywords_for_set,
    update_keyword_set,
)
from app.services.perplexity_client import PerplexityClient
from app.services.claude_client import ClaudeClient
from app.services.companies_enrichment import apply_company_profile, enrich_company
from app.services.dadata_mcp import check_dadata_mcp_server
from app.tasks.celery_app import celery_app

router = APIRouter()


class SearchSettingsUpdate(BaseModel):
    perplexity_limit_sources: int | None = None
    perplexity_limit_leads: int | None = None
    perplexity_query_limit: int | None = None


@router.get("/health", tags=["system"])
async def health_check() -> dict:
    """Check the availability of the service.

    A dictionary with service status.
    """

    return {"status": "ok"}


@router.get("/tenders", response_model=list[TenderRead], tags=["tenders"])
async def list_tenders(
    limit: int = 50,
    offset: int = 0,
    region: str | None = None,
    search: str | None = None,
    status: str | None = None,
    winner: str | None = None,
    participant: str | None = None,
    stage: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    start_date_from: date | None = None,
    start_date_to: date | None = None,
    end_date_from: date | None = None,
    end_date_to: date | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[TenderRead]:
    """Get a list of tenders with pagination.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param region: Regional filter.
    :param search: Search line on ID/stat.
    :param position: tender/project stage.
    :param status: Tender status.
    :param winner: Winner filter.
    :param partipant: Filter by participant.
    :param budget_min: Minimum budget.
    :param budget_max: Maximum budget.
    :param start_date_from: Initial date (from).
    :param start_date_to: Initial date (before).
    :param end_date_from: Final date (from).
    :param end_date_to: Final date (before).
    :param session: Asynchronous database session.
    A list of tenders.
    """

    query = select(Tender)
    if region:
        query = query.where(Tender.region.ilike(f"%{region}%"))
    if search:
        query = query.where(
            or_(
                Tender.tender_id.ilike(f"%{search}%"),
                Tender.status.ilike(f"%{search}%"),
                Tender.title.ilike(f"%{search}%"),
            )
        )
    if status:
        query = query.where(Tender.status.ilike(f"%{status}%"))
    if winner:
        query = query.where(Tender.winner.ilike(f"%{winner}%"))
    if stage:
        query = query.where(Tender.stage.ilike(f"%{stage}%"))
    if budget_min is not None:
        query = query.where(Tender.budget >= budget_min)
    if budget_max is not None:
        query = query.where(Tender.budget <= budget_max)
    if start_date_from is not None:
        query = query.where(Tender.start_date >= start_date_from)
    if start_date_to is not None:
        query = query.where(Tender.start_date <= start_date_to)
    if end_date_from is not None:
        query = query.where(Tender.end_date >= end_date_from)
    if end_date_to is not None:
        query = query.where(Tender.end_date <= end_date_to)
    query = query.order_by(Tender.id.desc())
    result = await session.execute(query.offset(offset).limit(limit))
    tenders = list(result.scalars().all())
    if participant:
        filtered = []
        for item in tenders:
            participants = item.participants or []
            participants_text = " ".join([str(p) for p in participants])
            if participant.lower() in participants_text.lower():
                filtered.append(item)
        tenders = filtered
    return tenders


@router.post("/tenders", response_model=TenderRead, tags=["tenders"])
async def create_tender(
    payload: TenderCreate,
    session: AsyncSession = Depends(get_db_session),
) -> TenderRead:
    """Create tender.

    :param payload: Data tender for creation.
    :param session: Asynchronous database session.
    :return: A tender record has been created.
    """

    tender = Tender(**payload.model_dump())
    session.add(tender)
    await session.commit()
    await session.refresh(tender)
    return tender


@router.get("/tenders/{tender_id}", response_model=TenderRead, tags=["tenders"])
async def get_tender(
    tender_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> TenderRead:
    """Get a tender using an external identifier.

    :param tender_id: Tender Identifier (external).
    :param session: Asynchronous database session.
    Tender.
    """

    result = await session.execute(select(Tender).where(Tender.tender_id == tender_id))
    tender = result.scalars().first()
    if not tender:
        return {"error": "not_found"}
    return tender


@router.get("/companies", response_model=list[CompanyRead], tags=["companies"])
async def list_companies(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[CompanyRead]:
    """Get a list of companies with a pagination.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param session: Asynchronous database session.
    List of companies.
    """

    result = await session.execute(select(Company).offset(offset).limit(limit))
    return list(result.scalars().all())


@router.post("/companies/dedupe", tags=["companies"])
async def dedupe_companies_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Starting the deduction of companies.

    :param session: Asynchronous database session.
    :return: Scene statistics.
    """

    return await dedupe_companies(session)


@router.post("/companies", response_model=CompanyRead, tags=["companies"])
async def create_company(
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRead:
    """To create a company.

    :param payload: Company data for creation.
    :param session: Asynchronous database session.
    :return: Company's created record.
    """

    company = Company(**payload.model_dump())
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


@router.get("/dadata-mcp/check", tags=["companies"])
async def dadata_mcp_check() -> dict:
    """Check direct access to the MPData server (without OpenAI)).

    Helps to see if 424 returns due to Dadata's inefficiencies or OpenAI's.
    """
    return await check_dadata_mcp_server()


@router.post("/companies/enrich", tags=["companies"])
async def enrich_company_endpoint(
    inn: str | None = None,
    ogrn: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Enrich company data through Dadata and Rusprofile.

    Options can be transmitted in any combination; the service will try to collect
    maximum information from external sources.
    """

    profile = await enrich_company(
        session,
        inn=inn,
        ogrn=ogrn,
        email=email,
        phone=phone,
        name=name,
    )
    return profile


@router.post("/companies/enrich/auto", tags=["companies"])
async def enrich_companies_auto(
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    'Automatically enrich companies from database via Datata/Perplexity/Rusprofile.'

    result = await session.execute(select(Company).limit(limit))
    companies = list(result.scalars().all())
    updated = 0
    for company in companies:
        profile = await enrich_company(
            session,
            inn=company.inn,
            ogrn=company.ogrn,
            email=company.email,
            phone=company.phone,
            name=company.name,
        )
        apply_company_profile(company, profile)
        updated += 1
    await session.commit()
    return {"updated": updated}


@router.get("/projects", response_model=list[ProjectRead], tags=["projects"])
async def list_projects(
    limit: int = 50,
    offset: int = 0,
    region: str | None = None,
    stage: str | None = None,
    budget_min: float | None = None,
    budget_max: float | None = None,
    start_date_from: date | None = None,
    start_date_to: date | None = None,
    end_date_from: date | None = None,
    end_date_to: date | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectRead]:
    """Get a list of projects with pagination.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param region: Regional filter.
    :param stage: Project stage.
    :param budget_min: Minimum budget.
    :param budget_max: Maximum budget.
    :param start_date_from: Initial date (from).
    :param start_date_to: Initial date (before).
    :param end_date_from: Final date (from).
    :param end_date_to: Final date (before).
    :param session: Asynchronous database session.
    :return: List of projects.
    """

    query = select(Project)
    if region:
        query = query.where(Project.region.ilike(f"%{region}%"))
    if stage:
        query = query.where(Project.stage.ilike(f"%{stage}%"))
    if budget_min is not None:
        query = query.where(Project.budget >= budget_min)
    if budget_max is not None:
        query = query.where(Project.budget <= budget_max)
    if start_date_from is not None:
        query = query.where(Project.start_date >= start_date_from)
    if start_date_to is not None:
        query = query.where(Project.start_date <= start_date_to)
    if end_date_from is not None:
        query = query.where(Project.end_date >= end_date_from)
    if end_date_to is not None:
        query = query.where(Project.end_date <= end_date_to)
    query = query.order_by(Project.id.desc())
    result = await session.execute(query.offset(offset).limit(limit))
    return list(result.scalars().all())


@router.get("/projects/count", tags=["projects"])
async def count_projects(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Get the number of projects.

    :param session: Asynchronous database session.
    :return: Number of projects.
    """

    result = await session.execute(select(Project.id))
    return {"count": len(result.scalars().all())}


@router.post("/projects", response_model=ProjectRead, tags=["projects"])
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRead:
    """Create a project.

    :param payload: Project data for creation.
    :param session: Asynchronous database session.
    :return: Created project entry.
    """

    project = Project(**payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead, tags=["projects"])
async def get_project(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectRead:
    """Get an I.D. project.

    :param project_id: Project Identifier.
    :param session: Asynchronous database session.
    :return: Project.
    """

    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        return {"error": "not_found"}
    return project


def _format_contact_block(name: str, emails: list[str], phones: list[str]) -> str:
    """Form a contact box for the report.

    :param name: Name of company.
    :param emails: Email contacts.
    :param phones: Phones.
    Contact string.
    """

    unique_phones = []
    for phone in phones:
        if phone and phone not in unique_phones:
            unique_phones.append(phone)
    unique_emails = []
    for email in emails:
        if email and email not in unique_emails:
            unique_emails.append(email)
    parts = [name]
    if unique_phones:
        parts.append(f"Tel: {', '.join(unique_phones[:2])}")
    if unique_emails:
        parts.append(f"email: {', '.join(unique_emails[:2])}")
    return " | ".join([p for p in parts if p])


def _infer_industry(project_name: str) -> str:
    """Identify the industry by the name of the project.

    :param project_name: Name of project.
    Industry.
    """

    return 'Construction'


def _clean_companies_for_report(companies: list[str]) -> list[str]:
    """Clear the company list for the report.

    :param companies: Raw names.
    :return: Cleared list.
    """

    cleaned_list: list[str] = []
    for name in companies:
        cleaned = " ".join(name.replace("\n", " ").split()).strip()
        if not cleaned:
            continue
        if len(cleaned) > 120:
            continue
        cleaned_list.append(cleaned)
    return cleaned_list


def _normalize_company_key(raw_name: str) -> str:
    """Normalize the company's key to protect against takeoff.

    :param raw_name: Reference name.
    :return: Normalized key.
    """

    lowered = raw_name.lower()
    cleaned = re.sub(r"[\"'«»]", "", lowered)
    cleaned = cleaned.replace("общество с ограниченной ответственностью", "ооо")
    cleaned = cleaned.replace("акционерное общество", "ао")
    cleaned = cleaned.replace("публичное акционерное общество", "пао")
    cleaned = cleaned.replace("закрытое акционерное общество", "зао")
    cleaned = re.sub(r"[^a-zа-я0-9]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()


def _normalize_project_key(raw_name: str) -> str:
    """Normalize the project key to protect against duplicates.

    :param raw_name: Reference name.
    :return: Normalized key.
    """

    lowered = raw_name.lower()
    cleaned = re.sub(r"[\"'«»]", "", lowered)
    cleaned = re.sub(r"[^a-zа-я0-9]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()




def _is_project_name(name: str) -> bool:
    """Check that the line is similar to the name of the project.

    :param name: Name of project.
    True, if it's like a project.
    """

    cleaned = " ".join(name.split()).strip()
    if len(cleaned) > 140:
        return False
    lowered = cleaned.lower()
    stop_words = (
        "конференц",
        "выставк",
        "форум",
        "семинар",
        "совещан",
        "круглый стол",
        "подписка",
        "журнал",
    )
    if any(word in lowered for word in stop_words):
        return False
    keywords = (
        "проект",
        "строительств",
        "реконструкц",
        "капремонт",
        "ремонт",
        "мост",
        "дорог",
        "аэропорт",
        "обход",
        "объект",
        "комплекс",
        "завод",
        "станция",
    )
    return any(word in lowered for word in keywords)


def _parse_ruble_amount(raw_value: str) -> float | None:
    """Unload the amount in the rubles from the line.

    :param raw_value: Raw amounts.
    :return: Amount in rubles or None.
    """

    lowered = raw_value.lower().replace(" ", "")
    if any(token in lowered for token in ("usd", 'Total', "$", "eur", 'Euro', "€")):
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)", lowered)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    multiplier = 1.0
    if "тыс" in lowered:
        multiplier = 1_000.0
    if "млн" in lowered:
        multiplier = 1_000_000.0
    if "млрд" in lowered:
        multiplier = 1_000_000_000.0
    if "руб" in lowered or "₽" in lowered or "р." in lowered or "р" in lowered:
        return value * multiplier
    return value * multiplier


def _extract_geo_materials_budget(texts: list[str]) -> float | None:
    """Budget for Geosynthic Materials.

    :param texts: List of articles.
    :return: Amount in rubles or None.
    """

    for text in texts:
        lowered = text.lower()
        if "геосинтет" not in lowered:
            continue
        for match in re.finditer(
            r"\d+(?:[.,]\d+)?\s*(?:тыс|млн|млрд)?\s*руб",
            lowered,
        ):
            parsed = _parse_ruble_amount(match.group(0))
            if parsed:
                return parsed
    return None


def _project_score(project: Project) -> tuple[int, float]:
    """Assess the quality of the completion of the project.

    :param project: Project.
    :return: Corte (score, budget).
    """

    score = 0
    if project.region:
        score += 1
    if project.stage:
        score += 1
    if project.start_date:
        score += 1
    if project.end_date:
        score += 1
    if project.budget:
        score += 2
    return score, project.budget or 0.0


def _get_company_contacts(company: Company | None) -> tuple[str, str]:
    """Get the phone and e-mail to the company.

    :param company: Company.
    :return: Phone and email.
    """

    if not company:
        return "", ""
    contacts = company.contacts or {}
    emails = contacts.get("emails") or []
    phones = contacts.get("phones") or []
    email_value = emails[0] if emails else (company.email or "")
    phone_value = phones[0] if phones else (company.phone or "")
    return phone_value, email_value


def _build_company_cells(
    name: str | None,
    companies_map: dict[str, Company],
) -> tuple[str, str, str]:
    """Form a company cell for the report.

    :param name: Name of company.
    :param companies_map: Companies' Handbook on Normalized Key.
    Name, telephone, e-mail.
    """

    if not name:
        return "", "", ""
    normalized_key = _normalize_company_key(name)
    company = companies_map.get(normalized_key)
    phone, email = _get_company_contacts(company)
    return name, phone, email


def _filter_emails_for_article(article: Article, emails: list[str]) -> list[str]:
    """Remove e-mail domains of the source from the list.

    :param article: Source article.
    :param emails: Email list.
    :return: Filtered list.
    """

    free_domains = {
        "gmail.com",
        "mail.ru",
        "bk.ru",
        "list.ru",
        "inbox.ru",
        "yandex.ru",
        "yandex.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
    }
    sources = load_sources_config()
    source_domains = set()
    for item in sources:
        url = item.get("url", "")
        if not url:
            continue
        domain_part = url.replace("https://", "").replace("http://", "").split("/")[0]
        source_domains.add(domain_part.replace("www.", ""))
    domain = ""
    if article.url:
        domain = article.url.replace("https://", "").replace("http://", "").split("/")[0]
        domain = domain.replace("www.", "")
    filtered = []
    for email in emails:
        email_lower = email.lower()
        email_domain = email_lower.split("@")[-1] if "@" in email_lower else ""
        if email_domain in free_domains:
            continue
        if domain and email_domain.endswith(domain):
            continue
        if email_domain in source_domains:
            continue
        filtered.append(email)
    return filtered


async def _build_project_report(session: AsyncSession) -> list[dict]:
    """Form the lines of the project report.

    :param session: Asynchronous database session.
    :return: List of lines of report.
    """

    projects = (await session.execute(select(Project))).scalars().all()
    companies_db = (await session.execute(select(Company))).scalars().all()
    articles = (await session.execute(select(Article))).scalars().all()
    tenders = (await session.execute(select(Tender))).scalars().all()
    report_rows: list[dict] = []
    seen_projects: set[str] = set()
    companies_map: dict[str, Company] = {}
    for company in companies_db:
        if company.normalized_name:
            companies_map[company.normalized_name] = company
        else:
            companies_map[_normalize_company_key(company.name)] = company

    grouped_projects: dict[str, Project] = {}
    for project in projects:
        if not _is_project_name(project.name):
            continue
        project_key = _normalize_project_key(project.name)
        existing = grouped_projects.get(project_key)
        if not existing:
            grouped_projects[project_key] = project
            continue
        if _project_score(project) > _project_score(existing):
            grouped_projects[project_key] = project
    if not grouped_projects and projects:
        for project in projects:
            project_key = _normalize_project_key(project.name)
            existing = grouped_projects.get(project_key)
            if not existing:
                grouped_projects[project_key] = project
            elif _project_score(project) > _project_score(existing):
                grouped_projects[project_key] = project

    project_items: list[dict] = []
    for project in grouped_projects.values():
        # For the project report, we're looking at local articles,
        # It's not an external search for Perplexity.
        related_articles = [
            a for a in articles if a.text and project.name.lower() in (a.text or "").lower()
        ]
        latest_date = None
        for article in related_articles:
            if article.published_at:
                if latest_date is None or article.published_at > latest_date:
                    latest_date = article.published_at
        project_items.append(
            {
                "project": project,
                "related": related_articles,
                "latest_date": latest_date,
            }
        )

    sorted_projects = sorted(
        project_items,
        key=lambda item: (
            item["latest_date"] or datetime.min,
            item["project"].id,
        ),
        reverse=True,
    )
    for idx, item in enumerate(sorted_projects, start=1):
        project = item["project"]
        project_key = _normalize_project_key(project.name)
        if project_key in seen_projects:
            continue
        seen_projects.add(project_key)
        related = item["related"]
        related_texts: list[str] = []
        for article in related:
            if article.text:
                related_texts.append(article.text)

        customer_name = project.customer_name
        customer_phone = project.customer_phone
        customer_email = project.customer_email
        investor_name = project.investor_name
        investor_phone = project.investor_phone
        investor_email = project.investor_email
        contractor_name = project.contractor_name
        contractor_phone = project.contractor_phone
        contractor_email = project.contractor_email

        geo_budget = _extract_geo_materials_budget(related_texts)
        budget_value = project.budget
        if isinstance(budget_value, str):
            try:
                budget_value = float(budget_value.replace(" ", "").replace(",", "."))
            except ValueError:
                budget_value = None
        if budget_value is None:
            budget_value = 0
        report_rows.append(
            {
                'No.': idx,
                'Industry': _infer_industry(project.name),
                'Customer': customer_name or "",
                'Customer phone': customer_phone or "",
                'Customer email': customer_email or "",
                'Investor': investor_name or "",
                'Investor phone': investor_phone or "",
                'Investor email': investor_email or "",
                'Contractor': contractor_name or "",
                'Contractor phone': contractor_phone or "",
                'Contractor email': contractor_email or "",
                'Project name': project.name,
                'Project description': project.description or "",
                'Source': ", ".join(project.source_urls or []),
                'Region': project.region or "",
                'Total investment, RUB': budget_value,
                'Estimated geosynthetic materials, RUB': geo_budget,
                'Implementation period': project.end_date,
                'Current project stage': project.stage or "",
            }
        )
    return report_rows


@router.get("/reports/projects", tags=["reports"])
async def report_projects(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    """Receive the project report in table format.

    :param session: Asynchronous database session.
    :return: List of lines of report.
    """

    missing_stmt = (
        select(Project.id)
        .where(
            or_(
                Project.description.is_(None),
                Project.customer_name.is_(None),
                Project.contractor_name.is_(None),
                Project.customer_email.is_(None),
                Project.customer_phone.is_(None),
            )
        )
        .limit(1)
    )
    missing = (await session.execute(missing_stmt)).scalars().first()
    if missing:
        celery_app.send_task("tpis.enrich_projects_now", kwargs={"limit": 200})
    return await _build_project_report(session)


@router.post("/projects/clear", tags=["projects"])
async def clear_projects(session: AsyncSession = Depends(get_db_session)) -> dict:
    'Completely clear projects, tenders and caches of canonical names.'

    project_count = await session.execute(select(func.count(Project.id)))
    project_total = int(project_count.scalar() or 0)
    tender_count = await session.execute(select(func.count(Tender.id)))
    tender_total = int(tender_count.scalar() or 0)
    await session.execute(text("DELETE FROM project_title_cache"))
    await session.execute(delete(MatchLink))
    await session.execute(delete(Tender))
    await session.execute(delete(Project))
    await session.commit()
    return {"projects_deleted": project_total, "tenders_deleted": tender_total}


@router.post("/automation/start_test", tags=["automation"])
async def automation_start_test() -> dict:
    'Start a full cycle with one Perplexity request.'

    from app.tasks.celery_app import celery_app

    update_search_settings(
        {
            "perplexity_limit_sources": 10,
            "perplexity_limit_leads": 10,
            "perplexity_query_limit": 10,
        }
    )
    celery_app.send_task("tpis.update_cycle")
    return {"queued": True, "mode": "test"}


@router.get("/export/projects/excel", tags=["export"])
async def export_projects_excel(session: AsyncSession = Depends(get_db_session)):
    """Unload the projects to Excel using a template.

    :param session: Asynchronous database session.
    :return: XLSX file.
    """

    records = await _build_project_report(session)
    file_path = export_projects_excel_template(records, name="projects_template")
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="projects_template.xlsx",
    )


@router.get("/export/dossier/project/{project_id}", tags=["export"])
async def export_project_dossier(
    project_id: int,
    format: str = "pdf",
    session: AsyncSession = Depends(get_db_session),
):
    """Form a project file.

    :param project_id: Project Identifier.
    :param form: discharge format (pdf, doxx).
    :param session: Asynchronous database session.
    :return: Project file.
    """

    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        return {"error": "not_found"}
    sections = {
        'Project parameters': [
            f"Name: {project.name}",
            f"Region: {project.region or ''}",
            f"Stage: {project.stage or ''}",
            f"Budget: {project.budget or ''}",
            f"Start: {project.start_date or ''}",
            f"End: {project.end_date or ''}",
        ]
    }
    if format == "docx":
        file_path = export_dossier_docx('Project file', sections, f"project_{project_id}")
    else:
        file_path = export_dossier_pdf('Project file', sections, f"project_{project_id}")
    return FileResponse(path=file_path)


@router.get("/projects/{project_id}/related", tags=["projects"])
async def get_project_related(
    project_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get related project name through Perplexity/Claude.

    :param project_id: Project Identifier.
    :param session: Asynchronous database session.
    :return: List of related articles.
    """

    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().first()
    if not project:
        return []
    # We use the same LLM approach as for common semantic search,
    # but without additional key sets and with a fixed focus on articles/news.
    base_prompt = (
        "You're a research assistant on construction projects. "
        'Find articles and news that are clearly related to the project, '
        'and return the most relevant results.'
    )
    perplexity_client = PerplexityClient()
    raw_results = await perplexity_client.search(
        project.name,
        system_prompt=base_prompt,
        keywords=[],
        max_results=20,
    )
    claude_client = ClaudeClient()
    ranked = await claude_client.rank_results(project.name, raw_results, keywords=[])
    return ranked[:10]


@router.get("/articles", response_model=list[ArticleRead], tags=["articles"])
async def list_articles(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[ArticleRead]:
    """Get a list of articles with pagination.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param session: Asynchronous database session.
    :return: List of articles.
    """

    stmt = (
        select(Article)
        .order_by(nulls_last(Article.published_at.desc()), Article.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/articles", response_model=ArticleRead, tags=["articles"])
async def create_article(
    payload: ArticleCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ArticleRead:
    """Create an article.

    :param payload: These articles are for creation.
    :param session: Asynchronous database session.
    :return: An article created.
    """

    article = Article(**payload.model_dump())
    session.add(article)
    await session.commit()
    await session.refresh(article)
    return article


@router.get("/matches", response_model=list[MatchLinkRead], tags=["matches"])
async def list_matches(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[MatchLinkRead]:
    """Get a list of the links to the tender article with the pagination.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param session: Asynchronous database session.
    It's a list of connections.
    """

    result = await session.execute(select(MatchLink).offset(offset).limit(limit))
    return list(result.scalars().all())


@router.get("/matches/pending", response_model=list[MatchLinkRead], tags=["matches"])
async def list_pending_matches(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[MatchLinkRead]:
    """Get a list of unconfirmed connections.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param session: Asynchronous database session.
    List of unconfirmed links.
    """

    result = await session.execute(
        select(MatchLink).where(MatchLink.approved.is_(False)).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


@router.post("/matches", response_model=MatchLinkRead, tags=["matches"])
async def create_match(
    payload: MatchLinkCreate,
    session: AsyncSession = Depends(get_db_session),
) -> MatchLinkRead:
    """Create a link between the tender and the article.

    :param payload: Data of the connection for creation.
    :param session: Asynchronous database session.
    :return: Created communication tape.
    """

    match = MatchLink(**payload.model_dump())
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


@router.post("/matches/{match_id}/approve", response_model=MatchLinkRead, tags=["matches"])
async def approve_match(
    match_id: int,
    reviewer: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> MatchLinkRead:
    """Confirm the operator's connection.

    :param match_id: Communication Identifier.
    :param reviewer: Operator Identifier.
    :param session: Asynchronous database session.
    :return: Updated link.
    """

    result = await session.execute(select(MatchLink).where(MatchLink.id == match_id))
    match = result.scalars().first()
    if not match:
        return {"error": "not_found"}
    match.approved = True
    match.reviewer = reviewer
    match.reviewed_at = datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    await session.commit()
    await session.refresh(match)
    return match


@router.get("/sources", response_model=list[SourceRead], tags=["sources"])
async def list_sources(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[SourceRead]:
    """Get a list of sources.

    :param limit: Maximum number of entries in response.
    :param offset: Offset from sample start.
    :param session: Asynchronous database session.
    List of sources.
    """

    stmt = select(Source).order_by(Source.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/sources/count", tags=["sources"])
async def count_sources(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Get a lot of sources.

    :param session: Asynchronous database session.
    :return: Number of sources.
    """

    result = await session.execute(select(Source.id))
    return {"count": len(result.scalars().all())}


@router.post("/sources", response_model=SourceRead, tags=["sources"])
async def create_source(
    payload: SourceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> SourceRead:
    """Create a source.

    :param payload: Source data for creation.
    :param session: Asynchronous database session.
    :return: Source created.
    """

    source = Source(**payload.model_dump())
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@router.post("/sources/bootstrap", tags=["sources"])
async def bootstrap_sources(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Load the YAML sources of the configuration.

    :param session: Asynchronous database session.
    :return: Number of sources added.
    """

    items = load_sources_config()
    created = 0
    for item in items:
        url = item.get("url")
        if not url:
            continue
        exists = await session.execute(select(Source).where(Source.url == url))
        if exists.scalars().first():
            continue
        session.add(
            Source(
                name=item.get("name"),
                url=url,
                kind=item.get("kind", "html"),
                status=item.get("status", "active"),
                auto_discovered=item.get("auto_discovered", False),
            )
        )
        created += 1
    await session.commit()
    return {"created": created}


@router.get("/sources/discover", tags=["sources"])
async def discover_sources(
    query: str = Query(..., min_length=2),
) -> list[dict[str, str]]:
    """Find sources by the key word.

    :param query: Search phrase.
    :return: List of sources found.
    """

    service = DiscoveryService()
    results = await service.search_sources(query)
    mapped: list[dict[str, str]] = []
    for item in results:
        url = str(item.get("url") or item.get("link") or "")
        name = str(item.get("title") or item.get("name") or url)
        kind = "rss" if "rss" in url or "feed" in url else "html"
        mapped.append({"name": name, "url": url, "kind": kind, "status": "candidate"})
    return mapped


@router.post("/sources/discover/run", tags=["sources"])
async def run_discover_sources() -> dict:
    'Start background auto-detection of sources.'

    from app.tasks.celery_app import celery_app

    celery_app.send_task("tpis.discover_sources_cycle")
    return {"queued": True}


@router.get("/keywords", tags=["sources"])
async def get_keywords() -> dict:
    """Get Keyword Vocabularies from YAML-config (for interoperability)).

    :return: Keyword dictionary.
    """

    return load_keywords_config()


@router.get(
    "/keyword-sets",
    response_model=list[SearchKeywordSetRead],
    tags=["search"],
)
async def list_keyword_sets_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> list[SearchKeywordSetRead]:
    """Get all keywords/prompts.

    In the first application, automatically initializes the basic set
    from config/keywords.yaml (construction_keywords) if the database is empty.
    """

    await bootstrap_keyword_sets_from_yaml(session)
    sets = await list_keyword_sets(session)
    return [SearchKeywordSetRead.model_validate(item) for item in sets]


@router.post(
    "/keyword-sets",
    response_model=SearchKeywordSetRead,
    tags=["search"],
)
async def create_keyword_set_endpoint(
    payload: SearchKeywordSetCreate,
    session: AsyncSession = Depends(get_db_session),
) -> SearchKeywordSetRead:
    'Create a new set of key words.'

    keywords_payload = payload.keywords or []
    keywords = [(item.text, item.weight) for item in keywords_payload]
    created = await create_keyword_set(
        session,
        name=payload.name,
        description=payload.description,
        created_by=payload.created_by,
        keywords=keywords,
    )
    return SearchKeywordSetRead.model_validate(created)


@router.put(
    "/keyword-sets/{set_id}",
    response_model=SearchKeywordSetRead,
    tags=["search"],
)
async def update_keyword_set_endpoint(
    set_id: int,
    payload: SearchKeywordSetUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> SearchKeywordSetRead | dict:
    'Update the existing set of key words.'

    keywords = (
        [(item.text, item.weight) for item in payload.keywords] if payload.keywords else None
    )
    updated = await update_keyword_set(
        session,
        set_id,
        name=payload.name,
        description=payload.description,
        created_by=payload.created_by,
        keywords=keywords,
    )
    if not updated:
        return {"error": "not_found"}
    return SearchKeywordSetRead.model_validate(updated)


@router.delete(
    "/keyword-sets/{set_id}",
    tags=["search"],
)
async def delete_keyword_set_endpoint(
    set_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    'Delete the set of key words.'

    ok = await delete_keyword_set(session, set_id)
    return {"deleted": ok}


@router.get("/compare", tags=["compare"])
async def compare_entities(
    tender_id: str,
    article_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Compare tender fields with articles.

    :param tender_id: Tender Identifier (external).
    :param article_id: Article Identifier.
    :param session: Asynchronous database session.
    :return: Vocabulary of Field Discrepancies.
    """

    tender_result = await session.execute(select(Tender).where(Tender.tender_id == tender_id))
    article_result = await session.execute(select(Article).where(Article.id == article_id))
    tender = tender_result.scalars().first()
    article = article_result.scalars().first()
    if not tender or not article:
        return {"error": "not_found"}
    diff = diff_fields(
        {
            "region": tender.region,
            "budget": tender.budget,
            "currency": tender.currency,
            "status": tender.status,
        },
        {"title": article.title, "url": article.url},
        ["region", "budget", "currency", "status", "title", "url"],
    )
    return {"diff": diff}


@router.get("/search/semantic", tags=["search"])
async def semantic_search_endpoint(
    query: str,
    scope: str = "articles",
    limit: int = 10,
    keyword_set_id: int | None = None,
    mode: str = "generic",
    perplexity_limit: int | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Perplexity search and Claude ranking.

    Perplexity is responsible for collecting relevant results: projects, tenders, government purchase orders and public procurement
    (magazines, media, procurement portals). Claude pre-sells and classifys.

    :Param query: Search request (may be generated automatically)).
    :Param scope: Search Area (Articles/tenders/projects/all).
    :param limit: Maximum results.
    :Param keyword_set_id: Keyword Set Identifier.
    :Param mode: Mode: Generic/journals/media/tenders_projects/gov_orders.
    :param session: Asynchronous database session.
    A list of coincidences.
    """

    keywords = await resolve_keywords_for_set(session, keyword_set_id)

    base_prompt = (
        "You're an assistant for research on construction projects, tenders and state orders on the Russian-language Internet. "
        'Look for articles, announcements and pages on projects, procurement (44-FZ, 223-FZ), government orders. '
        'Give me real links and headlines.'
    )
    mode = (mode or "generic").lower()
    if mode == "journals":
        base_prompt += (
            ' Give priority to industry journals and publications on construction and infrastructure.'
        )
    elif mode == "media":
        base_prompt += (
            ' Give priority to the media and regional portals with news on construction projects and tenders.'
        )
    elif mode == "tenders_projects":
        base_prompt += (
            ' Focus on commercial tenders, procurement and construction projects in Russia.'
        )
    elif mode == "gov_orders":
        base_prompt += (
            ' Focus on state orders and public procurement: EIS, 44-FZ, 223-FZ, Russian procurement, customers, contractors, contacts.'
        )

    if scope == "articles":
        base_prompt += ' Special focus on news articles and analysis.'
    elif scope == "tenders":
        base_prompt += ' Special focus on tenders and procurement procedures.'
    elif scope == "projects":
        base_prompt += ' Special focus on project descriptions and investment plans.'

    # The Perplexity Challenge for Primary Search
    perplexity_client = PerplexityClient()
    max_results = max(limit, perplexity_limit or 0) if perplexity_limit else max(limit, 20)
    raw_results = await perplexity_client.search(
        query,
        system_prompt=base_prompt,
        keywords=keywords,
        max_results=max_results,
    )

    # Ran and possible classification via Claude
    claude_client = ClaudeClient()
    ranked = await claude_client.rank_results(query, raw_results, keywords=keywords)
    # Cut to the requested limit while maintaining order
    return ranked[:limit]


@router.get("/export/tenders", tags=["export"])
async def export_tenders(
    format: str = "csv",
    session: AsyncSession = Depends(get_db_session),
):
    """Unload the tender list to the file.

    :param formula: Unload format (csv, xlsx, parquet).
    :param session: Asynchronous database session.
    :return: Unload file.
    """

    result = await session.execute(select(Tender))
    records = [
        {
            "tender_id": t.tender_id,
            "region": t.region,
            "budget": t.budget,
            "currency": t.currency,
            "status": t.status,
        }
        for t in result.scalars().all()
    ]
    file_path = export_records(records, name="tenders", fmt=format)
    return FileResponse(path=file_path)


@router.get("/export/dossier/company/{company_id}", tags=["export"])
async def export_company_dossier(
    company_id: int,
    format: str = "pdf",
    session: AsyncSession = Depends(get_db_session),
):
    """Form a company file.

    :param company_id: Company Identifier.
    :param form: discharge format (pdf, doxx).
    :param session: Asynchronous database session.
    :return: Company file.
    """

    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalars().first()
    if not company:
        return {"error": "not_found"}
    sections = {
        'General information': [
            f"Name: {company.name}",
            f"INN: {company.inn or ''}",
            f"Phone: {company.phone or ''}",
            f"Email: {company.email or ''}",
            f"Address: {company.address or ''}",
        ]
    }
    if format == "docx":
        file_path = export_dossier_docx('Company file', sections, f"company_{company_id}")
    else:
        file_path = export_dossier_pdf('Company file', sections, f"company_{company_id}")
    return FileResponse(path=file_path)


@router.get("/automation/status", tags=["automation"])
async def automation_status() -> dict:
    """Get a state of automation.

    :return: Automation status.
    """

    return get_state()


@router.post("/automation/start", tags=["automation"])
async def automation_start() -> dict:
    """Run the manual automation cycle.

    :return: Launch status.
    """

    from app.tasks.celery_app import celery_app

    celery_app.send_task("tpis.update_cycle")
    return {"queued": True}


@router.post("/automation/enable", tags=["automation"])
async def automation_enable() -> dict:
    """Put the automation on.

    :return: Updated state.
    """

    return set_enabled(True)


@router.post("/automation/stop", tags=["automation"])
async def automation_stop() -> dict:
    """Shut down the automation.

    :return: Updated state.
    """

    return set_enabled(False)


@router.get("/search/settings", tags=["search"])
async def search_settings() -> dict:
    return get_search_settings()


@router.put("/search/settings", tags=["search"])
async def update_search_settings_endpoint(payload: SearchSettingsUpdate) -> dict:
    return update_search_settings(payload.dict())


@router.get("/export/dossier/tender/{tender_id}", tags=["export"])
async def export_tender_dossier(
    tender_id: str,
    format: str = "pdf",
    session: AsyncSession = Depends(get_db_session),
):
    """Form a tender file.

    :param tender_id: External tender identifier.
    :param form: discharge format (pdf, doxx).
    :param session: Asynchronous database session.
    :return: Tender file file.
    """

    result = await session.execute(select(Tender).where(Tender.tender_id == tender_id))
    tender = result.scalars().first()
    if not tender:
        return {"error": "not_found"}
    sections = {
        'Tender parameters': [
            f"ID: {tender.tender_id}",
            f"Name: {tender.title or ''}",
            f"Region: {tender.region or ''}",
            f"Budget: {tender.budget or ''} {tender.currency or ''}",
            f"Status: {tender.status or ''}",
            f"Buyer: {tender.customer or ''}",
            f"Winner: {tender.winner or ''}",
        ]
    }
    if format == "docx":
        file_path = export_dossier_docx('Tender file', sections, f"tender_{tender_id}")
    else:
        file_path = export_dossier_pdf('Tender file', sections, f"tender_{tender_id}")
    return FileResponse(path=file_path)


@router.post("/nlp/extract", tags=["nlp"])
async def nlp_extract(payload: TextRequestCreate) -> dict:
    """Extract entities from text.

    :param payload: An object with text for processing.
    :Return: Dictionary with extracted essences.
    """

    entities = await extract_entities(payload.text)
    return {
        "projects": entities.projects,
        "companies": entities.companies,
        "persons": entities.persons,
        "emails": entities.emails,
        "phones": entities.phones,
        "money": entities.money,
        "dates": entities.dates,
    }


@router.post("/nlp/classify", tags=["nlp"])
async def nlp_classify(payload: TextRequestCreate) -> dict:
    """Classify text by content type.

    :param payload: An object with text for processing.
    :return: Class-marked dictionary.
    """

    label = await classify_text(payload.text)
    return {"label": label}


@router.post("/ingest/seldon", tags=["ingest"])
async def ingest_seldon(
    limit: int = 100,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Import data from Seldon API.

    :param limit: Maximum number of tenders.
    :param session: Asynchronous database session.
    :return: Import statistics.
    """

    client = SeldonClient()
    return await ingest_tenders(session, client, limit=limit)


@router.post("/ingest/sources", tags=["ingest"])
async def ingest_sources_endpoint(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Import data from media sources.

    :param session: Asynchronous database session.
    :return: Statistics on imported articles.
    """

    count = await ingest_sources(session)
    return {"articles_processed": count}


@router.post("/match/run", tags=["matching"])
async def run_matching(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Start a comparison of tenders and articles.

    :param session: Asynchronous database session.
    :return: Number of links established.
    """

    created = await match_tenders_and_articles(session)
    return {"matches_created": created}


@router.get("/ingest/diagnostics", tags=["ingest"])
async def ingest_diagnostics(session: AsyncSession = Depends(get_db_session)) -> dict:
    """Search and Parsing Diagnostics: Why Few Tenders/Projects.

    Shows: number of sources, articles, tenders, projects; outcome of last cycle;
    Whether Seldon and Perplexity. Parser handles all sources without a status filter.
    """
    settings = get_settings()
    state = get_state()
    sources_total_r = await session.execute(select(func.count(Source.id)))
    sources_total = (sources_total_r.scalar() or 0) or 0
    articles_r = await session.execute(select(func.count(Article.id)))
    articles_count = (articles_r.scalar() or 0) or 0
    tenders_r = await session.execute(select(func.count(Tender.id)))
    tenders_count = (tenders_r.scalar() or 0) or 0
    projects_r = await session.execute(select(func.count(Project.id)))
    projects_count = (projects_r.scalar() or 0) or 0
    seldon_ok = bool(
        settings.seldon_base_url
        and settings.seldon_api_key
        and "PASTE_SELDON_TOKEN_HERE" not in (settings.seldon_api_key or "")
    )
    perplexity_ok = bool(getattr(settings, "perplexity_api_key", None))
    return {
        "sources_total": sources_total,
        "articles_count": articles_count,
        "tenders_count": tenders_count,
        "projects_count": projects_count,
        "automation_enabled": state.get("enabled", True),
        "last_run_at": state.get("last_run_at"),
        "last_result": state.get("last_result"),
        "seldon_configured": seldon_ok,
        "perplexity_configured": perplexity_ok,
    }
