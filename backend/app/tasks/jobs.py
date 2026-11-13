"""Фоновые задания Celery.

Автор: Maxi-online
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services.automation_state import (
    acquire_enrich_lock,
    acquire_lock,
    is_enabled,
    release_enrich_lock,
    release_lock,
    update_last_run,
)
from app.services.dedupe_companies import dedupe_companies
from app.services.dedupe_projects import dedupe_projects
from app.services.pipeline import (
    enrich_projects_missing,
    ingest_perplexity_leads,
    ingest_sources,
    match_tenders_and_articles,
)
from app.services.seldon_client import SeldonClient
from app.models import Company, Source
from app.services.companies_enrichment import apply_company_profile, enrich_company
from app.services.config_loader import load_keywords_config
from app.services.discovery import DiscoveryService
from app.services.search_settings import get_search_settings
from app.services.http_client import HttpClient
from app.services.seldon_service import ingest_tenders

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

MEDIA_KEYWORDS = (
    "журнал",
    "издание",
    "новости",
    "портал",
    "медиа",
    "пресс",
    "news",
    "press",
    "journal",
    "magazine",
    "media",
)


def _is_media_source(name: str, url: str) -> bool:
    """Проверить, что источник похож на СМИ/журнал.

    :param name: Название источника.
    :param url: URL источника.
    :return: True, если это СМИ.
    """

    text = f"{name} {url}".lower()
    return any(keyword in text for keyword in MEDIA_KEYWORDS)


def _extract_feed_links(html: str, base_url: str) -> list[str]:
    """Извлечь RSS/Atom ссылки из HTML.

    :param html: HTML страницы.
    :param base_url: Базовый URL для относительных ссылок.
    :return: Список RSS/Atom ссылок.
    """

    pattern = re.compile(
        r"<link[^>]+rel=[\"']alternate[\"'][^>]+type=[\"']application/(?:rss|atom)\+xml[\"'][^>]+href=[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    links = []
    for href in pattern.findall(html):
        links.append(urljoin(base_url, href))
    return links


def _base_domain_url(url: str) -> str:
    """Получить базовый URL домена.

    :param url: Любой URL.
    :return: Базовый URL домена.
    """

    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _normalize_source_url(url: str) -> str:
    """Нормализовать URL источника для дедупликации."""

    cleaned = url.strip()
    if cleaned.endswith("/") and len(cleaned) > 8:
        cleaned = cleaned.rstrip("/")
    return cleaned


async def _discover_sources(
    session: AsyncSession,
    allow_all: bool,
    *,
    probe_feeds: bool = True,
    max_results: int = 1000,
) -> dict[str, int]:
    """Автообнаружение источников по ключевым словам."""

    keywords = load_keywords_config().get("construction_keywords", [])
    search_settings = get_search_settings()
    query_limit = int(search_settings.get("perplexity_query_limit", 0) or 0)
    # Ограничиваем число запросов только если лимит задан; иначе берём все ключевые слова (больше источников и лидов).
    if query_limit > 0:
        keywords = list(keywords)[:query_limit]
    # Если лимит не задан или 0 — используем все ключевые слова из config/keywords.yaml
    service = DiscoveryService()
    client = HttpClient()
    created = 0
    found = 0
    existing = await session.execute(select(Source.url))
    known_urls = {_normalize_source_url(url) for (url,) in existing.all() if url}
    async def _insert_source(
        name: str,
        url: str,
        kind: str,
        status: str,
        auto_discovered: bool,
    ) -> bool:
        stmt = (
            insert(Source)
            .values(
                name=name,
                url=url,
                kind=kind,
                status=status,
                auto_discovered=auto_discovered,
            )
            .on_conflict_do_nothing(index_elements=[Source.url])
        )
        result = await session.execute(stmt)
        return bool(result.rowcount)

    for keyword in keywords:
        try:
            results = await service.search_sources(keyword, max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discovery error for %s: %s", keyword, exc)
            continue
        found += len(results)
        for item in results:
            url = str(item.get("url") or item.get("link") or "")
            if not url:
                continue
            normalized_url = _normalize_source_url(url)
            if normalized_url in known_urls:
                continue
            name = str(item.get("title") or item.get("name") or url)
            if len(name) > 256:
                parsed = urlparse(url)
                name = parsed.netloc or url
            if not allow_all and not _is_media_source(name, url):
                continue
            kind = "rss" if "rss" in url or "feed" in url else "html"
            status = "active"
            if kind == "html":
                base_url = _base_domain_url(url)
                if probe_feeds:
                    try:
                        html = await client.get_text(url)
                        feeds = _extract_feed_links(html, url)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Feed detect error for %s: %s", url, exc)
                        feeds = []
                    if not feeds:
                        feeds = await _probe_feed_urls(client, base_url)
                    if feeds:
                        for feed_url in feeds:
                            inserted = await _insert_source(
                                name=name,
                                url=feed_url,
                                kind="rss",
                                status="active",
                                auto_discovered=True,
                            )
                            known_urls.add(_normalize_source_url(feed_url))
                            if inserted:
                                created += 1
                        continue
                url = base_url
                status = "active"
            inserted = await _insert_source(
                name=name,
                url=url,
                kind=kind,
                status=status,
                auto_discovered=True,
            )
            known_urls.add(normalized_url)
            if inserted:
                created += 1
        # Коммитим по ключевому слову, чтобы прогресс был виден сразу
        await session.commit()
    return {"created": created, "found": found}


async def _probe_feed_urls(client: HttpClient, base_url: str) -> list[str]:
    """Проверить стандартные URL RSS/Atom.

    :param client: HTTP клиент.
    :param base_url: Базовый URL домена.
    :return: Найденные RSS/Atom ссылки.
    """

    candidates = ("rss", "rss.xml", "feed", "feed.xml", "atom.xml")
    feeds: list[str] = []
    for suffix in candidates:
        probe = urljoin(base_url, suffix)
        try:
            text = await client.get_text(probe)
        except Exception:  # noqa: BLE001
            continue
        lowered = text.lower()
        if "<rss" in lowered or "<feed" in lowered:
            feeds.append(probe)
    return feeds


@celery_app.task(name="tpis.update_cycle")
def update_cycle() -> str:
    """Запустить полный цикл обновления данных.

    :return: Статус выполнения задачи.
    """

    logger.info("Update cycle started")

    settings = get_settings()

    async def _run_cycle() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                if not is_enabled():
                    logger.warning("Cycle skipped: automation_disabled")
                    return {"skipped": True, "reason": "automation_disabled"}
                if not acquire_lock():
                    logger.warning("Cycle skipped: cycle_locked (другой цикл ещё выполняется)")
                    return {"skipped": True, "reason": "cycle_locked"}
                seldon_stats: dict = {"skipped": True}
                if (
                    settings.seldon_base_url
                    and settings.seldon_base_url != "https://api.seldon.ru"
                    and settings.seldon_api_key
                    and "PASTE_SELDON_TOKEN_HERE" not in (settings.seldon_api_key or "")
                ):
                    try:
                        logger.info("Cycle step: ingest_tenders (Seldon)")
                        seldon_stats = await ingest_tenders(session, SeldonClient(), limit=200)
                        logger.info("Cycle step: Seldon done, created=%s updated=%s", seldon_stats.get("created"), seldon_stats.get("updated"))
                    except Exception as e:
                        logger.exception("Cycle step Seldon failed: %s", e)
                has_perplexity = bool(getattr(settings, "perplexity_api_key", None))
                if has_perplexity:
                    try:
                        logger.info("Cycle step: discover_sources + perplexity_leads")
                        search_settings = get_search_settings()
                        max_sources = int(search_settings.get("perplexity_limit_sources") or 0) or 100_000
                        max_leads = int(search_settings.get("perplexity_limit_leads") or 0) or 100_000
                        discovered_stats = await _discover_sources(
                            session,
                            allow_all=True,
                            probe_feeds=False,
                            max_results=max_sources,
                        )
                        leads_stats = await ingest_perplexity_leads(
                            session,
                            max_results=max_leads,
                        )
                        logger.info("Cycle step: discovery created=%s leads=%s", discovered_stats.get("created"), leads_stats)
                    except Exception as e:
                        logger.exception("Cycle step discovery/perplexity_leads failed: %s", e)
                        discovered_stats = {"created": 0, "found": 0}
                        leads_stats = {"projects": 0, "tenders": 0}
                else:
                    discovered_stats = {"created": 0, "found": 0}
                    leads_stats = {"projects": 0, "tenders": 0}
                try:
                    logger.info("Cycle step: ingest_sources (парсинг всех активных RSS/sitemap, без лимитов)")
                    sources_count = await ingest_sources(session)
                    logger.info("Cycle step: ingest_sources done, articles_processed=%s", sources_count)
                except Exception as e:
                    logger.exception("Cycle step ingest_sources failed (основа системы): %s", e)
                    raise
                try:
                    logger.info("Cycle step: enrich_projects_missing, dedupe, companies, match")
                    projects_enriched = await enrich_projects_missing(session, limit=200)
                    projects_deduped = await dedupe_projects(session)
                    companies_deduped = await dedupe_companies(session)
                    enriched_companies = 0
                    result = await session.execute(select(Company).limit(100))
                    companies = list(result.scalars().all())
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
                        enriched_companies += 1
                    await session.commit()
                    matches_count = await match_tenders_and_articles(session)
                    logger.info("Cycle step: all done, matches=%s", matches_count)
                except Exception as e:
                    logger.exception("Cycle step enrich/dedupe/match failed: %s", e)
                    raise
                return {
                    "seldon": seldon_stats,
                    "sources_discovered": discovered_stats.get("created", 0),
                    "sources_found": discovered_stats.get("found", 0),
                    "perplexity_leads": leads_stats,
                    "sources": sources_count,
                    "projects_enriched": projects_enriched.get("updated", 0),
                    "projects_deduped": projects_deduped.get("merged", 0),
                    "companies_deduped": companies_deduped.get("merged", 0),
                    "companies_enriched": enriched_companies,
                    "matches": matches_count,
                }
        except Exception as e:
            logger.exception("Update cycle failed (исключение в _run_cycle): %s", e)
            raise
        finally:
            release_lock()
            await engine.dispose()

    result = asyncio.run(_run_cycle())
    if isinstance(result, dict) and result.get("reason") == "cycle_locked":
        logger.info("Cycle skipped due to lock: %s", result)
        return str(result)
    update_last_run(result if isinstance(result, dict) else {"result": result})
    logger.info("Cycle finished: %s", result)
    return str(result)


@celery_app.task(name="tpis.enrich_projects_now")
def enrich_projects_now(limit: int = 200) -> str:
    """Запустить дозаполнение проектов вне основного цикла.

    :param limit: Лимит проектов за проход.
    :return: Статус выполнения задачи.
    """

    logger.info("Enrich projects now started")
    settings = get_settings()

    async def _run_enrich() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                if not is_enabled():
                    return {"skipped": True, "reason": "automation_disabled"}
                if not acquire_enrich_lock():
                    return {"skipped": True, "reason": "enrich_locked"}
                stats = await enrich_projects_missing(session, limit=limit)
                return stats
        finally:
            release_enrich_lock()
            await engine.dispose()

    result = asyncio.run(_run_enrich())
    logger.info("Enrich projects now finished: %s", result)
    return str(result)


@celery_app.task(name="tpis.discover_sources_cycle")
def discover_sources_cycle() -> str:
    """Запустить цикл автообнаружения источников.

    :return: Статус выполнения задачи.
    """

    logger.info("Discover sources cycle started")
    settings = get_settings()

    async def _run_discovery() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                has_perplexity = bool(getattr(settings, "perplexity_api_key", None))
                if not settings.discovery_search_url and not has_perplexity:
                    return {"skipped": True, "reason": "discovery_url_missing"}
                allow_all = bool(has_perplexity) or bool(
                    settings.discovery_search_url and "engine=google_news" in settings.discovery_search_url
                )
                search_settings = get_search_settings()
                max_sources = int(search_settings.get("perplexity_limit_sources") or 0) or 100_000
                created_stats = await _discover_sources(
                    session,
                    allow_all=allow_all,
                    probe_feeds=not allow_all,
                    max_results=max_sources,
                )
                return created_stats
        finally:
            await engine.dispose()

    result = asyncio.run(_run_discovery())
    logger.info("Discover sources cycle finished: %s", result)
    return str(result)
