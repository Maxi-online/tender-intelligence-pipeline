"""High-level company enrichment service (Dadata + Rusprofile + LLM)).

Objective: To collect maximum information on the company on the DIN/E-mail/telephone/dominant
from Dadata and Rusprofile and return an aggregate profile that can be
Save it in the database or display it in the frontend.
"""

from __future__ import annotations

from typing import Any
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.services.dadata_client import (
    DadataClient,
    _normalize_dadata_email_company,
    _normalize_dadata_party,
)
from app.services.dadata_mcp import enrich_company_with_mcp
from app.services.perplexity_client import PerplexityClient
from app.services.llm_processing import (
    extract_contacts_from_mcp_payload,
    extract_contacts_from_snippets,
)

logger = logging.getLogger(__name__)


async def enrich_company(
    session: AsyncSession,
    *,
    inn: str | None = None,
    ogrn: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Collect maximum company information from external sources.

    :param session: Session of the database (for possible future recording of the company)).
    :param inn: INN company.
    :param ogrn: The company's DEAD.
    :param email: Corporate email.
    :param phone: Telephone (for Rusprofile-proxie)
    :param name: Name of company.
    :Retorn: Company aggregate profile with source markings.
    """

    _ = session  # Until we automatically save, just return the profile
    logger.info(
        "enrich_company: inn=%s ogrn=%s email=%s phone=%s name=%s",
        inn,
        ogrn,
        email,
        phone,
        name,
    )

    sources: list[dict[str, Any]] = []

    canonical_name = None
    canonical_inn = inn
    canonical_ogrn = ogrn
    canonical_address = None
    canonical_email = email
    canonical_phone = phone

    # ----Dadata: search by name (if no IDN/DRN) ---
    if not (inn or ogrn) and name:
        try:
            dadata_client = DadataClient()
            suggestions = await dadata_client.suggest_party(query=name, count=5)
            logger.info("Dadata suggest results: name=%s count=%s", name, len(suggestions))
            if suggestions:
                first = suggestions[0] or {}
                data = first.get("data") or {}
                canonical_name = canonical_name or first.get("value") or name
                canonical_inn = data.get("inn") or canonical_inn
                canonical_ogrn = data.get("ogrn") or canonical_ogrn
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata suggest error for %s: %s", name, exc)

    # ----Dadata: OIN/DOE--
    dadata_profile: dict[str, Any] | None = None
    if canonical_inn or canonical_ogrn:
        query = canonical_inn or canonical_ogrn or ""
        try:
            dadata_client = DadataClient()
            parties = await dadata_client.find_party_by_inn_ogrn(query=query, count=5)
            logger.info("Dadata party results: query=%s count=%s", query, len(parties))
            if parties:
                dadata_profile = _normalize_dadata_party(parties[0])
                sources.append(dadata_profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata party error for %s: %s", query, exc)
    else:
        logger.info("Dadata party skipped: no inn/ogrn")

    # ---Dadata: e-mail company ---
    dadata_email_profile: dict[str, Any] | None = None
    if email:
        try:
            dadata_client = DadataClient()
            email_companies = await dadata_client.find_company_by_email(email=email)
            logger.info("Dadata email results: email=%s count=%s", email, len(email_companies))
            if email_companies:
                dadata_email_profile = _normalize_dadata_email_company(email_companies[0])
                sources.append(dadata_email_profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata email error for %s: %s", email, exc)

    # --- Dadata: Affiliated INS Founder/Head Companies ---
    affiliated_companies: list[dict[str, Any]] = []
    if inn:
        try:
            dadata_client = DadataClient()
            affiliated = await dadata_client.find_affiliated(inn_person_or_org=inn, count=50)
            logger.info("Dadata affiliated results: inn=%s count=%s", inn, len(affiliated))
            for item in affiliated:
                data = item.get("data") or {}
                affiliated_companies.append(
                    {
                        "value": item.get("value"),
                        "inn": data.get("inn"),
                        "ogrn": data.get("ogrn"),
                        "okved": data.get("okved"),
                        "status": (data.get("state") or {}).get("status"),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata affiliated error for %s: %s", inn, exc)

    # ----Dadata MCP: INN/DOGN card ---
    if canonical_inn or canonical_ogrn:
        try:
            query = canonical_inn or canonical_ogrn or ""
            mcp_payload = await enrich_company_with_mcp(query)
            if mcp_payload:
                sources.append({"source": "dadata_mcp", "payload": mcp_payload})
                logger.info("Dadata MCP payload: query=%s size=%s", query, len(mcp_payload))
                if (
                    canonical_email is None
                    or canonical_phone is None
                    or canonical_inn is None
                    or canonical_ogrn is None
                    or canonical_name is None
                    or canonical_address is None
                ):
                    extracted = await extract_contacts_from_mcp_payload(mcp_payload)
                    logger.info(
                        "Dadata MCP contacts extracted: email=%s phone=%s inn=%s ogrn=%s name=%s",
                        bool(extracted.get("email")),
                        bool(extracted.get("phone")),
                        bool(extracted.get("inn")),
                        bool(extracted.get("ogrn")),
                        bool(extracted.get("name")),
                    )
                    logger.info(
                        "MCP->GPT summary: %s",
                        json.dumps(
                            {
                                "name": extracted.get("name"),
                                "inn": extracted.get("inn"),
                                "ogrn": extracted.get("ogrn"),
                                "email": extracted.get("email"),
                                "phone": extracted.get("phone"),
                                "address": extracted.get("address"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    canonical_email = canonical_email or extracted.get("email")
                    canonical_phone = canonical_phone or extracted.get("phone")
                    canonical_inn = canonical_inn or extracted.get("inn")
                    canonical_ogrn = canonical_ogrn or extracted.get("ogrn")
                    canonical_name = canonical_name or extracted.get("name")
                    canonical_address = canonical_address or extracted.get("address")
        except Exception:  # noqa: BLE001
            logger.warning("Dadata MCP error for %s", canonical_inn or canonical_ogrn)

    # ---Perplexity: web search for company and Rusprofile ---
    try:
        perplexity = PerplexityClient()
        query_parts = [p for p in [inn, ogrn, email, phone, name] if p]
        if query_parts:
            query = " ".join(query_parts)
            search_results = await perplexity.search(
                f"{query} site:rusprofile.ru",
                system_prompt=(
                    "You're looking for company cards on rusprofile.ru and official pages. "
                    'Just return the relevant links.'
                ),
                keywords=[],
                max_results=10,
            )
            logger.info(
                "Perplexity rusprofile results: query=%s count=%s", query, len(search_results)
            )
            if search_results:
                sources.append(
                    {
                        "source": "perplexity_rusprofile",
                        "results": search_results,
                    }
                )
                snippets = [
                    f"{item.get('title')}\n{item.get('snippet')}\n{item.get('url')}"
                    for item in search_results
                    if item.get("title") or item.get("snippet") or item.get("url")
                ]
                if snippets and (canonical_email is None or canonical_phone is None):
                    extracted = await extract_contacts_from_snippets(snippets)
                    logger.info(
                        "Rusprofile contacts extracted: email=%s phone=%s inn=%s ogrn=%s",
                        bool(extracted.get("email")),
                        bool(extracted.get("phone")),
                        bool(extracted.get("inn")),
                        bool(extracted.get("ogrn")),
                    )
                    canonical_email = canonical_email or extracted.get("email")
                    canonical_phone = canonical_phone or extracted.get("phone")
                    canonical_inn = canonical_inn or extracted.get("inn")
                    canonical_ogrn = canonical_ogrn or extracted.get("ogrn")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Perplexity company search error: %s", exc)

    # --- Repeated Dadata after extracting INN/OGRN/Email from Rusprofile ---
    if not dadata_profile and (canonical_inn or canonical_ogrn):
        query = canonical_inn or canonical_ogrn or ""
        try:
            dadata_client = DadataClient()
            parties = await dadata_client.find_party_by_inn_ogrn(query=query, count=5)
            logger.info("Dadata party retry: query=%s count=%s", query, len(parties))
            if parties:
                dadata_profile = _normalize_dadata_party(parties[0])
                sources.append(dadata_profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata party retry error for %s: %s", query, exc)
    elif not dadata_profile:
        logger.info("Dadata party skipped: no inn/ogrn")

    if not dadata_email_profile and canonical_email:
        try:
            dadata_client = DadataClient()
            email_companies = await dadata_client.find_company_by_email(email=canonical_email)
            logger.info(
                "Dadata email retry: email=%s count=%s", canonical_email, len(email_companies)
            )
            if email_companies:
                dadata_email_profile = _normalize_dadata_email_company(email_companies[0])
                sources.append(dadata_email_profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dadata email retry error for %s: %s", canonical_email, exc)
    elif not dadata_email_profile:
        logger.info("Dadata email skipped: no email")

    # --- Repeated Dadata MCP after extracting INN/OGRN ---
    if canonical_inn or canonical_ogrn:
        try:
            query = canonical_inn or canonical_ogrn or ""
            mcp_payload = await enrich_company_with_mcp(query)
            if mcp_payload:
                sources.append({"source": "dadata_mcp", "payload": mcp_payload})
                logger.info("Dadata MCP retry payload: query=%s size=%s", query, len(mcp_payload))
                if (
                    canonical_email is None
                    or canonical_phone is None
                    or canonical_inn is None
                    or canonical_ogrn is None
                    or canonical_name is None
                    or canonical_address is None
                ):
                    extracted = await extract_contacts_from_mcp_payload(mcp_payload)
                    logger.info(
                        "Dadata MCP retry contacts extracted: email=%s phone=%s inn=%s ogrn=%s name=%s",
                        bool(extracted.get("email")),
                        bool(extracted.get("phone")),
                        bool(extracted.get("inn")),
                        bool(extracted.get("ogrn")),
                        bool(extracted.get("name")),
                    )
                    logger.info(
                        "MCP->GPT retry summary: %s",
                        json.dumps(
                            {
                                "name": extracted.get("name"),
                                "inn": extracted.get("inn"),
                                "ogrn": extracted.get("ogrn"),
                                "email": extracted.get("email"),
                                "phone": extracted.get("phone"),
                                "address": extracted.get("address"),
                            },
                            ensure_ascii=False,
                        ),
                    )
                    canonical_email = canonical_email or extracted.get("email")
                    canonical_phone = canonical_phone or extracted.get("phone")
                    canonical_inn = canonical_inn or extracted.get("inn")
                    canonical_ogrn = canonical_ogrn or extracted.get("ogrn")
                    canonical_name = canonical_name or extracted.get("name")
                    canonical_address = canonical_address or extracted.get("address")
        except Exception:  # noqa: BLE001
            logger.warning("Dadata MCP retry error for %s", canonical_inn or canonical_ogrn)
    else:
        logger.info("Dadata MCP skipped: no inn/ogrn")

    # ---- Total aggregate profile ---
    # Priority: Dadata party > Dadata email > Rusprofile > already known values
    if dadata_profile:
        canonical_name = dadata_profile.get("name") or canonical_name
        canonical_inn = dadata_profile.get("inn") or canonical_inn
        canonical_ogrn = dadata_profile.get("ogrn") or canonical_ogrn
        canonical_address = dadata_profile.get("address") or canonical_address
        if dadata_profile.get("emails"):
            canonical_email = dadata_profile["emails"][0]
        if dadata_profile.get("phones"):
            canonical_phone = dadata_profile["phones"][0]
    if not canonical_name and dadata_email_profile:
        canonical_name = dadata_email_profile.get("name")
    if not canonical_email and dadata_email_profile:
        canonical_email = dadata_email_profile.get("email")

    profile: dict[str, Any] = {
        "name": canonical_name or name,
        "inn": canonical_inn,
        "ogrn": canonical_ogrn,
        "address": canonical_address,
        "email": canonical_email,
        "phone": canonical_phone,
        "sources": sources,
        "affiliated_companies": affiliated_companies,
    }
    logger.info(
        "Enrich profile result: name=%s inn=%s ogrn=%s email=%s phone=%s sources=%s",
        profile.get("name"),
        bool(profile.get("inn")),
        bool(profile.get("ogrn")),
        bool(profile.get("email")),
        bool(profile.get("phone")),
        len(profile.get("sources") or []),
    )
    return profile


def apply_company_profile(company: Company, profile: dict[str, Any]) -> None:
    "Apply the enrichment profile to the company's record."

    if not company.inn and profile.get("inn"):
        company.inn = profile["inn"]
    if not company.ogrn and profile.get("ogrn"):
        company.ogrn = profile["ogrn"]
    if not company.address and profile.get("address"):
        company.address = profile["address"]
    if not company.email and profile.get("email"):
        company.email = profile["email"]
    if not company.phone and profile.get("phone"):
        company.phone = profile["phone"]
    contacts = company.contacts or {}
    contacts["external_sources"] = profile.get("sources") or []
    company.contacts = contacts


__all__ = ["enrich_company", "apply_company_profile"]

