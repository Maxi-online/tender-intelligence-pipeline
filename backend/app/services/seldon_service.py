"""A data import and mapping service from Seldon Tenders API.

Appointment: obtaining the most up-to-date information possible on customers and winners
(not participating in tenders). Purchases/Result, Protocols, Contracts
in the TK TPI scheme and storage in cache (SeldonPurchase) for a single REST API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.seldon_purchase import SeldonPurchase
from app.services.seldon_client import SeldonClient
from app.services.seldon_validation import filter_purchases_by_validation, validate_purchases_with_llm

logger = logging.getLogger(__name__)


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        return value
    try:
        return date_parser.parse(str(value), dayfirst=False)
    except Exception:
        return None


def _date_only(value: Any) -> Any:
    dt = _parse_date(value)
    return dt.date() if dt else None


def map_purchase_to_tpis_schema(raw: dict[str, Any]) -> dict[str, Any]:
    'Transform raw object purchase from Seldon to TK TPIS (for REST API)).'
    seldon_id = raw.get("seldonId") or raw.get("SeldonId")
    status = raw.get("status") or {}
    currency = raw.get("currency") or {}
    contract_type = raw.get("contractType") or {}
    organizer = raw.get("organizer") or {}
    if isinstance(organizer, dict):
        customer_name = organizer.get("name")
        customer_inn = organizer.get("inn")
    else:
        customer_name = customer_inn = None
    lots = raw.get("lotsList") or []
    if lots and not customer_name:
        first_lot = lots[0] if isinstance(lots[0], dict) else {}
        customers_list = first_lot.get("customersList") or []
        if customers_list and isinstance(customers_list[0], dict):
            org = customers_list[0].get("organization") or customers_list[0]
            customer_name = org.get("name") if isinstance(org, dict) else customer_name
            customer_inn = org.get("inn") if isinstance(org, dict) else customer_inn
    contact_info = raw.get("contactInfo")
    return {
        "tender_id": str(seldon_id) if seldon_id is not None else None,
        "title": raw.get("subject"),
        "budget": raw.get("purchasePrice"),
        "currency": currency.get("code") if isinstance(currency, dict) else None,
        "status": status.get("statusSeldon") or status.get("statusEIS"),
        "stage": contract_type.get("name") if isinstance(contract_type, dict) else None,
        "start_date": _date_only(raw.get("startDate")),
        "end_date": _date_only(raw.get("endDate")),
        "customer": customer_name,
        "source_url": raw.get("purchaseLink"),
        "contact_info": contact_info,
        "notification_number": raw.get("notificationNumber"),
    }


def map_purchase_to_model(raw: dict[str, Any]) -> dict[str, Any]:
    'Prepare fields to record SeldonPurchase from raw purchase.'
    seldon_id = raw.get("seldonId") or raw.get("SeldonId")
    if seldon_id is None:
        raise ValueError("purchase without seldonId")
    status = raw.get("status") or {}
    currency = raw.get("currency") or {}
    contract_type = raw.get("contractType") or {}
    organizer = raw.get("organizer") or {}
    if isinstance(organizer, dict):
        customer_name = organizer.get("name")
        customer_inn = organizer.get("inn")
    else:
        customer_name = customer_inn = None
    lots = raw.get("lotsList") or []
    if lots and not customer_name:
        first_lot = lots[0] if isinstance(lots[0], dict) else {}
        customers_list = first_lot.get("customersList") or []
        if customers_list and isinstance(customers_list[0], dict):
            org = customers_list[0].get("organization") or customers_list[0]
            if isinstance(org, dict):
                customer_name = org.get("name")
                customer_inn = org.get("inn")
    return {
        "seldon_id": int(seldon_id),
        "report_id": raw.get("reportId"),
        "notification_number": raw.get("notificationNumber"),
        "subject": raw.get("subject"),
        "purchase_price": raw.get("purchasePrice"),
        "currency_code": currency.get("code") if isinstance(currency, dict) else None,
        "status_code": status.get("codeStatusSeldon"),
        "status_name": status.get("statusSeldon") or status.get("statusEIS"),
        "stage": contract_type.get("name") if isinstance(contract_type, dict) else None,
        "start_date": _date_only(raw.get("startDate")),
        "end_date": _date_only(raw.get("endDate")),
        "customer_name": customer_name,
        "customer_inn": customer_inn,
        "source_url": raw.get("purchaseLink"),
        "contact_info": raw.get("contactInfo"),
        "raw_purchase": raw,
    }


def extract_participants_from_protocol(protocol: dict[str, Any] | None) -> list[dict[str, Any]]:
    'List of participants (organizations + dataApps admitted/resultType)).'
    if not protocol:
        return []
    lots_list = protocol.get("lotsList") or []
    participants: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lot in lots_list:
        if not isinstance(lot, dict):
            continue
        apps = lot.get("apps") or {}
        orgs = (apps.get("organizations") or []) if isinstance(apps, dict) else []
        data_apps = (apps.get("dataApps") or []) if isinstance(apps, dict) else []
        org_by_id: dict[int, dict] = {}
        for o in orgs:
            if isinstance(o, dict) and "id" in o:
                org_by_id[o["id"]] = o
        for app in data_apps:
            if not isinstance(app, dict):
                continue
            org_id = app.get("organizationId")
            org = org_by_id.get(org_id) if org_id is not None else None
            name = org.get("name") if isinstance(org, dict) else None
            inn = org.get("inn") if isinstance(org, dict) else None
            ogrn = (org.get("ogrnSeldon") or org.get("ogrnSource")) if isinstance(org, dict) else None
            admitted = app.get("admitted")
            result_type = app.get("resultType")
            key = (name or "", inn or "")
            if key in seen:
                continue
            seen.add(key)
            participants.append({
                "name": name,
                "inn": inn,
                "ogrn": ogrn,
                "admitted": admitted,
                "result_type": result_type,
            })
    return participants


def extract_winner_from_protocol(protocol: dict[str, Any] | None) -> dict[str, Any] | None:
    'From the protocol to extract the winner (request with the winner sign / resultType).'
    if not protocol:
        return None
    lots_list = protocol.get("lotsList") or []
    for lot in lots_list:
        if not isinstance(lot, dict):
            continue
        apps = lot.get("apps") or {}
        orgs = (apps.get("organizations") or []) if isinstance(apps, dict) else []
        data_apps = (apps.get("dataApps") or []) if isinstance(apps, dict) else []
        org_by_id: dict[int, dict] = {o["id"]: o for o in orgs if isinstance(o, dict) and "id" in o}
        for app in data_apps:
            if not isinstance(app, dict):
                continue
            result_type = str(app.get("resultType") or "").lower()
            if "победитель" in result_type or "winner" in result_type or app.get("admitted") is True:
                org_id = app.get("organizationId")
                org = org_by_id.get(org_id) if org_id is not None else None
                if org:
                    return {
                        "winner_name": org.get("name"),
                        "winner_inn": org.get("inn"),
                        "winner_ogrn": org.get("ogrnSeldon") or org.get("ogrnSource"),
                    }
    return None


def extract_winner_from_contract(contract: dict[str, Any] | None) -> dict[str, Any] | None:
    'The Contract for the Supplier as the Winner.'
    if not contract:
        return None
    contracts_list = contract.get("contracts") if isinstance(contract.get("contracts"), list) else []
    for c in contracts_list:
        if not isinstance(c, dict):
            continue
        supplier = c.get("supplier") or c.get("organization")
        if isinstance(supplier, dict):
            return {
                "winner_name": supplier.get("name"),
                "winner_inn": supplier.get("inn"),
                "winner_ogrn": supplier.get("ogrnSeldon") or supplier.get("ogrnSource"),
            }
    return None


async def sync_purchases_from_seldon(
    session: AsyncSession,
    client: SeldonClient,
    filter_id: int,
    date_from: str,
    date_to: str,
    subtype: int | None = None,
    validate_with_llm: bool | None = None,
) -> dict[str, int]:
    'Create an order for Purches, wait, download all pages and save in SeldonPurchase.'
    task_id = await client.create_order_purchases(filter_id, date_from, date_to, subtype)
    await client.wait_order_ready(task_id, "purchases")
    all_purchases = await client.get_purchases_result_all(task_id)
    if validate_with_llm is None:
        validate_with_llm = getattr(get_settings(), "seldon_validation_enabled", False)
    if validate_with_llm and all_purchases:
        validation_results = await validate_purchases_with_llm(all_purchases)
        all_purchases = filter_purchases_by_validation(all_purchases, validation_results)
        logger.info("Seldon sync: after LLM validation %s purchases left", len(all_purchases))
    created = 0
    updated = 0
    for raw in all_purchases:
        try:
            fields = map_purchase_to_model(raw)
        except (ValueError, TypeError) as e:
            logger.warning("Seldon purchase skip mapping: %s", e)
            continue
        existing = await session.execute(
            select(SeldonPurchase).where(SeldonPurchase.seldon_id == fields["seldon_id"])
        )
        row = existing.scalars().first()
        if row:
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = datetime.utcnow()
            updated += 1
        else:
            session.add(SeldonPurchase(**fields))
            created += 1
    await session.commit()
    return {"created": created, "updated": updated, "total": len(all_purchases)}


async def fetch_tenders_from_seldon(
    client: SeldonClient,
    filter_id: int,
    date_from: str,
    date_to: str,
    subtype: int | None = None,
) -> list[dict[str, Any]]:
    'Receive a purchase list from Seldon without storage in database (for testing/unloading)).'
    task_id = await client.create_order_purchases(filter_id, date_from, date_to, subtype)
    await client.wait_order_ready(task_id, "purchases")
    all_purchases = await client.get_purchases_result_all(task_id)
    return [map_purchase_to_tpis_schema(p) for p in all_purchases]


async def fetch_tenders(
    client: SeldonClient,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    'Reverse compatibility: obtain tenders (on filter_id and dates in paragraphs or silence)).'
    params = params or {}
    filter_id = params.get("filter_id")
    if filter_id is None:
        try:
            filters = await client.get_filters()
            filter_id = filters[0].get("filterId") if filters else None
        except Exception:
            filter_id = None
    if not filter_id:
        return []
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    date_from = params.get("date_from") or start.strftime("%Y-%m-%dT00:00:00.000000+00:00")
    date_to = params.get("date_to") or end.strftime("%Y-%m-%dT23:59:59.999999+00:00")
    return await fetch_tenders_from_seldon(client, int(filter_id), date_from, date_to)


def map_seldon_tender(raw: dict[str, Any]) -> dict[str, Any]:
    """Transform Seldon (already TPIS schema) to the Tender Fields.

    Used for inverse compatibility with ingest_tenders if caused by an old API.
    """
    start_date = raw.get("start_date")
    end_date = raw.get("end_date")
    return {
        "tender_id": str(raw.get("tender_id") or raw.get("id") or ""),
        "title": raw.get("title") or raw.get("name"),
        "region": raw.get("region"),
        "budget": raw.get("budget"),
        "currency": raw.get("currency"),
        "status": raw.get("status"),
        "stage": raw.get("stage"),
        "customer": raw.get("customer"),
        "winner": raw.get("winner"),
        "participants": raw.get("participants"),
        "contacts": raw.get("contacts"),
        "source_url": raw.get("source_url") or raw.get("url"),
        "start_date": _date_only(start_date) if start_date else None,
        "end_date": _date_only(end_date) if end_date else None,
    }


async def ingest_tenders(
    session: AsyncSession,
    client: SeldonClient,
    limit: int = 100,
) -> dict[str, int]:
    """Upload and save tenders to table listers (legacy)).

    If you need to unload from the real Seldon API, use sync_purchases_from_seldon
    pre-ordered for filter_id and dates.
    """
    try:
        filters_list = await client.get_filters()
        if not filters_list:
            return {"created": 0, "updated": 0}
        filter_id = filters_list[0].get("filterId")
        if filter_id is None:
            return {"created": 0, "updated": 0}
    except Exception as e:
        logger.warning("Seldon get_filters failed: %s", e)
        return {"created": 0, "updated": 0}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    date_from = start.strftime("%Y-%m-%dT00:00:00.000000+00:00")
    date_to = end.strftime("%Y-%m-%dT23:59:59.999999+00:00")
    items = await fetch_tenders_from_seldon(client, filter_id, date_from, date_to)
    from app.models.tender import Tender
    created = 0
    updated = 0
    for item in items[:limit]:
        tender_id = item.get("tender_id")
        if not tender_id:
            continue
        mapped = map_seldon_tender(item)
        mapped["quality_flag"] = bool(mapped.get("tender_id") and mapped.get("title"))
        result = await session.execute(select(Tender).where(Tender.tender_id == tender_id))
        existing = result.scalars().first()
        if existing:
            for key, value in mapped.items():
                setattr(existing, key, value)
            updated += 1
        else:
            session.add(Tender(**mapped))
            created += 1
    await session.commit()
    return {"created": created, "updated": updated}
