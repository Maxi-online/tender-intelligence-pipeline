"""REST API модуля Seldon по ТЗ TPIS.

Назначение: получение максимально свежей информации об участниках рынка — заказчиках
и победителях (не участие в тендерах). Эндпоинты: список закупок, детали, заказчики,
победители, участники, контакты по ИНН, связанные проекты.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models import Project, SeldonPurchase
from app.services.seldon_client import SeldonClient
from app.services.seldon_filter_advisor import recommend_filter_settings
from app.services.seldon_service import (
    extract_participants_from_protocol,
    extract_winner_from_protocol,
    map_purchase_to_tpis_schema,
    sync_purchases_from_seldon,
)

router = APIRouter(prefix="/seldon", tags=["seldon"])


class SeldonTenderListItem(BaseModel):
    tender_id: str
    title: str | None
    budget: float | None
    currency: str | None
    status: str | None
    stage: str | None
    start_date: date | None
    end_date: date | None
    customer: str | None
    source_url: str | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class SeldonTenderDetail(SeldonTenderListItem):
    notification_number: str | None = None
    contact_info: dict | list | None = None
    winner: str | None = None
    winner_inn: str | None = None
    winner_ogrn: str | None = None
    decision_date: date | None = None


class SeldonParticipant(BaseModel):
    name: str | None
    inn: str | None
    ogrn: str | None
    admitted: bool | None
    result_type: str | None


class SeldonWinnerResult(BaseModel):
    winner: str | None
    winner_inn: str | None
    winner_ogrn: str | None
    protocol: str | None
    decision: str | None
    decision_date: date | None


class SeldonContact(BaseModel):
    company_id: str | None
    inn: str | None
    name: str | None
    contact_person: str | None
    phone: str | None
    email: str | None


def _seldon_row_to_list_item(row: SeldonPurchase) -> dict[str, Any]:
    return {
        "tender_id": str(row.seldon_id),
        "title": row.subject,
        "budget": row.purchase_price,
        "currency": row.currency_code,
        "status": row.status_name,
        "stage": row.stage,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "customer": row.customer_name,
        "source_url": row.source_url,
        "updated_at": row.updated_at,
    }


@router.get("/tenders", response_model=list[SeldonTenderListItem])
async def list_seldon_tenders(
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    changed_since: datetime | None = Query(None),
) -> list[dict[str, Any]]:
    """Список тендеров из кэша Seldon с фильтрацией и пагинацией."""
    q = select(SeldonPurchase).order_by(SeldonPurchase.seldon_id.desc())
    if status:
        q = q.where(SeldonPurchase.status_name == status)
    if date_from:
        q = q.where(SeldonPurchase.start_date >= date_from)
    if date_to:
        q = q.where(SeldonPurchase.end_date <= date_to)
    if changed_since:
        q = q.where(SeldonPurchase.updated_at >= changed_since)
    q = q.offset(offset).limit(limit)
    result = await session.execute(q)
    rows = result.scalars().all()
    return [_seldon_row_to_list_item(r) for r in rows]


@router.get("/tenders/{tender_id}", response_model=SeldonTenderDetail)
async def get_seldon_tender(
    tender_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Детали тендера по ID (seldon_id)."""
    try:
        sid = int(tender_id)
    except ValueError:
        sid = 0
    result = await session.execute(select(SeldonPurchase).where(SeldonPurchase.seldon_id == sid))
    row = result.scalars().first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Тендер не найден")
    return {
        "tender_id": str(row.seldon_id),
        "title": row.subject,
        "budget": row.purchase_price,
        "currency": row.currency_code,
        "status": row.status_name,
        "stage": row.stage,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "customer": row.customer_name,
        "source_url": row.source_url,
        "updated_at": row.updated_at,
        "notification_number": row.notification_number,
        "contact_info": row.contact_info,
        "winner": row.winner_name,
        "winner_inn": row.winner_inn,
        "winner_ogrn": row.winner_ogrn,
        "decision_date": row.decision_date,
    }


@router.get("/tenders/{tender_id}/participants", response_model=list[SeldonParticipant])
async def get_seldon_tender_participants(
    tender_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """Участники по ID тендера (из кэша протокола)."""
    try:
        sid = int(tender_id)
    except ValueError:
        sid = 0
    result = await session.execute(select(SeldonPurchase).where(SeldonPurchase.seldon_id == sid))
    row = result.scalars().first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Тендер не найден")
    participants = row.participants
    if isinstance(participants, list):
        return [
            {
                "name": p.get("name") if isinstance(p, dict) else None,
                "inn": p.get("inn") if isinstance(p, dict) else None,
                "ogrn": p.get("ogrn") if isinstance(p, dict) else None,
                "admitted": p.get("admitted") if isinstance(p, dict) else None,
                "result_type": p.get("result_type") if isinstance(p, dict) else None,
            }
            for p in participants
        ]
    if row.raw_protocol:
        return extract_participants_from_protocol(row.raw_protocol)
    return []


@router.get("/tenders/{tender_id}/winner", response_model=SeldonWinnerResult)
async def get_seldon_tender_winner(
    tender_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Победитель и результаты торгов по ID тендера."""
    try:
        sid = int(tender_id)
    except ValueError:
        sid = 0
    result = await session.execute(select(SeldonPurchase).where(SeldonPurchase.seldon_id == sid))
    row = result.scalars().first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Тендер не найден")
    protocol_info = row.protocol_info or (row.raw_protocol if isinstance(row.raw_protocol, dict) else None)
    protocol_text = str(protocol_info)[:500] if protocol_info else None
    return {
        "winner": row.winner_name,
        "winner_inn": row.winner_inn,
        "winner_ogrn": row.winner_ogrn,
        "protocol": protocol_text,
        "decision": protocol_text,
        "decision_date": row.decision_date,
    }


@router.get("/contacts", response_model=list[SeldonContact])
async def get_seldon_contacts(
    session: AsyncSession = Depends(get_db_session),
    company_id: str | None = Query(None),
    inn: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Контакты контрагентов по company_id или ИНН (из кэша закупок)."""
    if not inn and not company_id:
        return []
    search_inn = (inn or company_id or "").strip()
    if not search_inn:
        return []
    q = select(SeldonPurchase).where(SeldonPurchase.customer_inn == search_inn).limit(50)
    result = await session.execute(q)
    rows = result.scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        ci = row.contact_info
        if isinstance(ci, dict):
            out.append({
                "company_id": str(row.seldon_id),
                "inn": row.customer_inn,
                "name": row.customer_name,
                "contact_person": ci.get("person"),
                "phone": ci.get("phone"),
                "email": ci.get("email"),
            })
        elif isinstance(ci, list) and ci and isinstance(ci[0], dict):
            for c in ci:
                out.append({
                    "company_id": str(row.seldon_id),
                    "inn": row.customer_inn,
                    "name": row.customer_name,
                    "contact_person": c.get("person"),
                    "phone": c.get("phone"),
                    "email": c.get("email"),
                })
    return out


@router.get("/tenders/{tender_id}/related-projects", response_model=list[dict])
async def get_seldon_tender_related_projects(
    tender_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """Связанные проекты по ID тендера (по совпадению заказчика с проектом)."""
    try:
        sid = int(tender_id)
    except ValueError:
        return []
    result = await session.execute(select(SeldonPurchase).where(SeldonPurchase.seldon_id == sid))
    row = result.scalars().first()
    if not row or not row.customer_name:
        return []
    name = (row.customer_name or "").strip()
    if not name:
        return []
    proj = await session.execute(
        select(Project).where(
            or_(
                Project.customer_name.ilike(f"%{name}%"),
                Project.name.ilike(f"%{name}%"),
            )
        ).limit(20)
    )
    projects = proj.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "normalized_name": p.normalized_name,
            "customer_name": p.customer_name,
        }
        for p in projects
    ]


class SeldonSyncRequest(BaseModel):
    filter_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    subtype: int | None = None
    search_goal: str | None = None


class SeldonRecommendRequest(BaseModel):
    search_goal: str


@router.post("/recommend-filters")
async def seldon_recommend_filters(body: SeldonRecommendRequest) -> dict[str, Any]:
    """По цели поиска (GPT-5-nano) подобрать настройки фильтров для максимально точной выгрузки."""
    client = SeldonClient()
    filters = await client.get_filters()
    return await recommend_filter_settings(body.search_goal, filters)


@router.post("/sync")
async def seldon_sync(
    body: SeldonSyncRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Создать заказ на выгрузку закупок в Seldon и сохранить результат в кэш.

    Можно передать либо явные filter_id/date_from/date_to, либо search_goal —
    тогда GPT подберёт настройки фильтров под цель поиска.
    """
    client = SeldonClient()
    filter_id = body.filter_id
    date_from = body.date_from
    date_to = body.date_to
    subtype = body.subtype

    if body.search_goal:
        rec = await recommend_filter_settings(body.search_goal, await client.get_filters())
        filter_id = rec.get("filter_id")
        date_from = rec.get("date_from")
        date_to = rec.get("date_to")
        subtype = rec.get("subtype")
        if filter_id is None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось подобрать фильтр по цели. Рекомендация: {rec.get('reason', '')}",
            )

    if filter_id is None or date_from is None or date_to is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="Укажите filter_id, date_from, date_to либо search_goal",
        )

    stats = await sync_purchases_from_seldon(
        session,
        client,
        int(filter_id),
        date_from,
        date_to,
        subtype,
    )
    return {"ok": True, "created": stats["created"], "updated": stats["updated"], "total": stats["total"]}


@router.get("/filters")
async def seldon_filters() -> list[dict[str, Any]]:
    """Список поисковых фильтров учётной записи Seldon."""
    client = SeldonClient()
    return await client.get_filters()
