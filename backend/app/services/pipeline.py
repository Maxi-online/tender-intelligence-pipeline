"""Пайплайн обработки данных: сбор, NLP, сопоставление.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
import hashlib
import logging

import re
import httpx
from dateutil import parser
from sqlalchemy import asc, nulls_first, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Article,
    Company,
    MatchLink,
    Project,
    ProjectTitleCache,
    Source,
    Tender,
)
from app.models.keyword import SearchKeywordSet
from app.services.config_loader import load_keywords_config
from app.services.html_parser import extract_text
from app.services.pdf_parser import extract_text_from_pdf
from app.services.http_client import HttpClient
from app.services.matching import compute_confidence
from app.services.keywords import bootstrap_keyword_sets_from_yaml
from app.services.openai_client import OpenAIClient
from app.services.llm_processing import (
    ExtractedEntities,
    classify_project_titles,
    classify_text,
    extract_entities,
    extract_contacts_from_snippets,
    extract_project_blocks_llm,
    extract_tender_blocks_llm,
    normalize_project_titles,
    select_primary_roles,
    summarize_project,
)
from app.services.perplexity_client import PerplexityClient
from app.services.deep_crawl import collect_internal_links
from app.services.rss_parser import parse_feed_content
from app.services.sitemap import parse_sitemap
from app.services.advanced_fetch import (
    discover_feeds_from_html,
    fetch_page_as_pdf_async,
)
from app.services.companies_enrichment import enrich_company
from app.services.search_settings import get_search_settings
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
MSK_TZ = ZoneInfo("Europe/Moscow")

# Неуспех обычного парсера = ничего не нашёл (0 блоков) или нашёл мало информации. Тогда подключаем LLM.
# Чуть ослабляем критерии, чтобы чаще добирать блоки через LLM.
MAX_BLOCKS_TO_TRIGGER_LLM = 8
MIN_TEXT_LEN_FOR_LLM = 400

# Лимитов на глобальный парсинг нет — обрабатываем все активные источники и все статьи.
MAX_SOURCES_PER_CYCLE = 1_000_000
MAX_ARTICLES_PER_CYCLE = 1_000_000

# Сигналы в тексте для гибкого поиска (без жёстких подписей «Заказчик:»)
_TENDER_SIGNALS_RE = re.compile(
    r"бюджет|сумма|млн\s|млрд|тыс\.?\s*руб|₽|победитель|подрядчик|заказчик|44-фз|223-фз|"
    r"тендер|закупк|контракт|генподрядчик|исполнитель|окончательная\s+цена|тип\s+закупки",
    re.IGNORECASE,
)
_PROJECT_SIGNALS_RE = re.compile(
    r"заказчик|подрядчик|инвестор|бюджет|строительство|реконструкция|капремонт|"
    r"проект|объект|инвестиции|путепровод|дорог|мост|капитальн",
    re.IGNORECASE,
)
_BUDGET_RE = re.compile(
    r"([\d\s.,]+)\s*(?:млрд|млн|тыс\.?)?\s*(?:руб|₽)?",
    re.IGNORECASE,
)


def _now_msk_naive() -> datetime:
    return datetime.now(MSK_TZ).replace(tzinfo=None)


async def _save_article(
    session: AsyncSession,
    source: Source | None,
    url: str,
    title: str | None,
    published_at: datetime | None,
    text: str | None,
) -> Article:
    """Создать или обновить статью.

    :param session: Асинхронная сессия БД.
    :param source: Источник данных.
    :param url: URL статьи.
    :param title: Заголовок статьи.
    :param published_at: Дата публикации.
    :param text: Полный текст статьи.
    :return: Сохраненная статья.
    """

    result = await session.execute(select(Article).where(Article.url == url))
    article = result.scalars().first()
    if not article:
        article = Article(url=url)
        session.add(article)
    article.source_id = source.id if source else None
    article.source = source.name if source else None
    article.title = title
    article.published_at = published_at
    article.text = text
    if text:
        entities = await extract_entities(text)
        entities.companies = _filter_company_names(entities.companies)
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
        await _upsert_companies(session, entities.companies, entities.emails, entities.phones, url)
        await _upsert_projects(session, entities.projects, article, text)
    try:
        await session.commit()
        await session.refresh(article)
    except IntegrityError:
        await session.rollback()
        existing = await session.execute(select(Article).where(Article.url == url))
        article = existing.scalars().first()
        if article:
            article.source_id = source.id if source else None
            article.source = source.name if source else None
            article.title = title
            article.published_at = published_at
            article.text = text
            await session.commit()
            await session.refresh(article)
    return article


def _get_parsing_keywords() -> list[str]:
    """Ключевые слова из config/keywords.yaml для гибкого парсинга."""
    try:
        cfg = load_keywords_config()
        keywords = list(cfg.get("construction_keywords") or [])
        regions = list(cfg.get("regions") or [])
        return keywords + regions
    except Exception:
        return ["строительство", "реконструкция", "капремонт", "тендер", "закупка", "проект"]


def _normalize_source_url(url: str) -> str:
    """Упрощённая нормализация URL источника для дедупликации.

    Используется при добавлении новых Source из лидов Perplexity. Срезаем якоря и
    параметры запроса, убираем хвостовой слэш.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    cleaned = parsed._replace(params="", query="", fragment="")
    normalized = urlunparse(cleaned)
    if normalized.endswith("/") and len(normalized) > 8:
        normalized = normalized.rstrip("/")
    return normalized


_CONSTRUCTION_THEMATIC_RE = re.compile(
    r"("
    r"строительн"  # строительство, строительный, строительные работы
    r"|реконструкц"  # реконструкция объектов
    r"|кап(итальн|ремонт)"  # капремонт, капитальный ремонт
    r"|объект[а-я\s]+капитальн"  # объекты капитального строительства
    r"|инженерн[а-я\s]+сет"  # инженерные сети
    r"|линейн[а-я\s]+объект"  # линейные объекты
    r"|дорог[а-я]*"  # дороги, дорожное строительство
    r"|магистрал"  # магистраль, магистральная дорога
    r"|эстакад"  # эстакада
    r"|путепровод"  # путепровод
    r"|развязк"  # транспортная развязка
    r"|тоннел"  # тоннель
    r"|мост(ов|овои?|ы)?"  # мост, мостовой переход
    r"|элементы\s+благоустройств"  # благоустройство территорий
    r"|школ[а-я]*|детсад|садик|детский\s+сад"  # соц. объекты
    r"|поликлиник[а-я]*|больниц[а-я]*|диагностическ[а-я]*\s+центр"
    r")",
    re.IGNORECASE,
)


def _is_construction_related(text: str) -> bool:
    """Жёсткий фильтр: оставить только строительную тематику / инфраструктуру."""
    if not text:
        return False
    return bool(_CONSTRUCTION_THEMATIC_RE.search(text))


def _split_text_into_chunks(text: str, max_chunk: int = 2800, min_chunk: int = 1) -> list[str]:
    """Разбить текст на фрагменты по абзацам или по размеру для гибкого поиска."""
    if not text or not text.strip():
        return []
    chunks: list[str] = []
    for part in re.split(r"\n\s*\n", text):
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chunk:
            chunks.append(part)
            continue
        pos = 0
        while pos < len(part):
            end = min(pos + max_chunk, len(part))
            slice_text = part[pos:end]
            if end < len(part):
                last_nl = slice_text.rfind("\n")
                if last_nl > min_chunk:
                    end = pos + last_nl + 1
                    slice_text = part[pos:end]
            pos = end
            if slice_text.strip():
                chunks.append(slice_text.strip())
    return chunks


def _extract_tender_blocks_flexible(text: str, keywords: list[str]) -> list[dict]:
    """Гибкое извлечение тендеров: любой фрагмент с ключевым словом и признаками закупки."""
    if not text or not keywords:
        return []
    chunks = _split_text_into_chunks(text)
    blocks: list[dict] = []
    seen_titles: set[str] = set()
    kw_pattern = re.compile("|".join(re.escape(kw.strip()) for kw in keywords if kw.strip()), re.I)
    for chunk in chunks:
        # Достаточно хотя бы одного ключевого слова ИЛИ хотя бы одного маркера тендера.
        if not (kw_pattern.search(chunk) or _TENDER_SIGNALS_RE.search(chunk)):
            continue
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        title = (lines[0][:512] if lines else chunk[:400].replace("\n", " ").strip()) or "Тендер"
        norm = title.lower().strip()[:200]
        if norm in seen_titles:
            continue
        seen_titles.add(norm)
        winner = None
        w_m = re.search(
            r"(?:победитель|подрядчик|исполнитель|генподрядчик)\s*[:\s]*([^\n\r\[\]]{3,120})",
            chunk,
            re.I,
        )
        if w_m:
            winner = re.sub(r"\[.*?\]|\(.*?\)", "", w_m.group(1)).strip()[:256]
        budget_val = None
        b_m = _BUDGET_RE.search(chunk)
        if b_m:
            num_s = b_m.group(1).replace(" ", "").replace(",", ".")
            try:
                budget_val = float(re.search(r"[\d.]+", num_s).group(0))
            except (ValueError, AttributeError):
                pass
        blocks.append({"title": title[:512], "winner": winner, "budget": budget_val, "status": None})
    return blocks


def _extract_project_blocks_flexible(text: str, keywords: list[str]) -> list[dict]:
    """Гибкое извлечение проектов: фрагмент с ключевым словом и признаками объекта/строительства."""
    if not text or not keywords:
        return []
    chunks = _split_text_into_chunks(text)
    blocks: list[dict] = []
    seen_keys: set[str] = set()
    kw_pattern = re.compile("|".join(re.escape(kw.strip()) for kw in keywords if kw.strip()), re.I)
    for chunk in chunks:
        # Достаточно хотя бы одного ключевого слова ИЛИ хотя бы одного маркера проекта.
        if not (kw_pattern.search(chunk) or _PROJECT_SIGNALS_RE.search(chunk)):
            continue
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        name = (lines[0][:512] if lines else chunk[:400].replace("\n", " ").strip()) or "Проект"
        norm = name.lower().strip()[:200]
        if norm in seen_keys:
            continue
        seen_keys.add(norm)
        customer = None
        c_m = re.search(r"заказчик\s*[:\s]*([^\n\r\[\]]{3,120})", chunk, re.I)
        if c_m:
            customer = re.sub(r"\[.*?\]|\(.*?\)", "", c_m.group(1)).strip()[:256]
        contractor = None
        p_m = re.search(r"(?:подрядчик|генподрядчик)\s*[:\s]*([^\n\r\[\]]{3,120})", chunk, re.I)
        if p_m:
            contractor = re.sub(r"\[.*?\]|\(.*?\)", "", p_m.group(1)).strip()[:256]
        investor = None
        i_m = re.search(r"инвестор\s*[:\s]*([^\n\r\[\]]{3,120})", chunk, re.I)
        if i_m:
            investor = re.sub(r"\[.*?\]|\(.*?\)", "", i_m.group(1)).strip()[:256]
        budget_val = None
        b_m = _BUDGET_RE.search(chunk)
        if b_m:
            num_s = b_m.group(1).replace(" ", "").replace(",", ".")
            try:
                budget_val = float(re.search(r"[\d.]+", num_s).group(0))
            except (ValueError, AttributeError):
                pass
        blocks.append({
            "name": name[:512],
            "customer_name": customer,
            "contractor_name": contractor,
            "investor_name": investor,
            "budget": budget_val,
        })
    return blocks


def _extract_tender_blocks_from_text(text: str) -> list[dict]:
    """Извлечь из текста блоки тендеров/закупок: строгие шаблоны + гибкий поиск по ключевым словам.

    Сначала применяются жёсткие маркеры (Закупка №, Заказчик: и т.д.), затем гибкий проход по
    ключевым словам из config/keywords.yaml и признакам закупки. Дубликаты по заголовку отсекаются.
    :param text: Текст страницы (HTML уже преобразован в текст).
    :return: Список словарей с полями title, winner, budget, status.
    """
    if not text or not text.strip():
        return []
    blocks: list[dict] = []
    # Ищем границы блоков: начало — «Закупка №» или «Тендер»
    start_pattern = re.compile(
        r"(Закупка\s*[№#]\s*[^\n]*|Тендер\s*[№#]?\s*[^\n]*)",
        re.IGNORECASE,
    )
    starts = [(m.start(), m.group(1).strip()) for m in start_pattern.finditer(text)]
    if not starts:
        # Нет явных маркеров — один блок на весь текст, если есть признаки тендера/закупки/госзаказа.
        if re.search(
            r"Генподрядчик|Окончательная\s+цена|Тип\s+закупки|44[-\s]*ФЗ|223[-\s]*ФЗ|тендер|закупк|аукцион|конкурс|лот|госзакупк|госзаказ",
            text,
            re.IGNORECASE,
        ):
            starts = [(0, "")]
    for i, (pos, header) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        part = text[pos:end].strip()
        # Заголовок блока или первая строка — как title
        if header and len(header) > 3:
            title = header[:512]
        else:
            title = "Тендер/закупка"
            for line in part.split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                if re.search(r"Генподрядчик|Окончательная\s+цена|Тип\s+закупки", line, re.I):
                    break
                title = line[:512] if len(line) <= 512 else line[:512].rstrip()
                break
            else:
                title = part[:400].replace("\n", " ").strip() or title
        winner = ""
        w_match = re.search(
            r"(?:Генподрядчик\s*\(поставщик\)|Победитель|Подрядчик|Исполнитель)\s*[:\s]*([^\n\r\[\]]+)",
            part,
            re.IGNORECASE,
        )
        if w_match:
            winner = re.sub(r"\[.*?\]|\(.*?\)", "", w_match.group(1)).strip()[:256]
        budget_val = None
        b_match = re.search(
            r"(?:Окончательная\s+цена|Цена|Бюджет|Сумма)\s*[:\s]*([\d\s.,]+)\s*₽?",
            part,
            re.IGNORECASE,
        )
        if b_match:
            num_str = b_match.group(1).replace(" ", "").replace(",", ".")
            try:
                budget_val = float(re.search(r"[\d.]+", num_str).group(0))
            except (ValueError, AttributeError):
                pass
        status = ""
        s_match = re.search(r"Тип\s+закупки\s*:\s*(\d+[- ]?ФЗ|\d+[- ]?ПП|[^\n\r]+)", part, re.I)
        if s_match:
            status = s_match.group(1).strip()[:64]
        if title or winner or budget_val:
            blocks.append({
                "title": (title[:512] if title else "Закупка"),
                "winner": winner or None,
                "budget": budget_val,
                "status": status or None,
            })
    # Гибкий проход по ключевым словам из config
    keywords = _get_parsing_keywords()
    flexible = _extract_tender_blocks_flexible(text, keywords)
    seen = {b.get("title", "").lower().strip()[:200] for b in blocks}
    for b in flexible:
        key = (b.get("title") or "").lower().strip()[:200]
        if key and key not in seen:
            seen.add(key)
            blocks.append(b)
    return blocks


def _extract_project_blocks_from_text(text: str) -> list[dict]:
    """Извлечь из текста блоки про проекты (коммерческие и государственные).

    Маркеры: проект, строительство, реконструкция, инвестиции, заказчик, подрядчик, инвестор.
    :param text: Текст страницы.
    :return: Список словарей с полями name, customer_name, contractor_name, investor_name, budget.
    """
    if not text or not text.strip():
        return []
    blocks: list[dict] = []
    # Границы блоков: «Проект», «Строительство», «Реконструкция», «Инвестиции», заголовки с заказчиком/подрядчиком
    start_pattern = re.compile(
        r"(Проект\s*[:\s]*[^\n]+|Строительство\s+[^\n]+|Реконструкция\s+[^\n]+|"
        r"Инвестиционн(?:ый|ая)\s+[^\n]+|Заказчик\s*[:\s]*[^\n]*|Подрядчик\s*[:\s]*[^\n]*)",
        re.IGNORECASE,
    )
    starts = [(m.start(), m.group(1).strip()) for m in start_pattern.finditer(text)]
    if not starts:
        # Если нет явных заголовков, но есть признаки проекта/строительства/инвестиций — берём весь текст как один блок.
        if re.search(
            r"заказчик|подрядчик|инвестор|бюджет|инвестиции|строительство|реконструкция|объект|капитальный ремонт",
            text,
            re.IGNORECASE,
        ):
            starts = [(0, "")]
    for i, (pos, header) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        part = text[pos:end].strip()
        name = ""
        if header and len(header) > 5 and not re.match(r"^(Заказчик|Подрядчик|Инвестор)\s*[:]", header, re.I):
            name = header[:512]
        else:
            for line in part.split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                if re.search(r"Заказчик\s*:|Подрядчик\s*:|Инвестор\s*:|Бюджет\s*:", line, re.I):
                    break
                name = line[:512] if len(line) <= 512 else line[:512].rstrip()
                break
            else:
                name = part[:400].replace("\n", " ").strip() or "Проект"
        customer = ""
        c_match = re.search(r"Заказчик\s*[:\s]*([^\n\r\[\]]+)", part, re.IGNORECASE)
        if c_match:
            customer = re.sub(r"\[.*?\]|\(.*?\)", "", c_match.group(1)).strip()[:256]
        contractor = ""
        p_match = re.search(r"Подрядчик\s*[:\s]*([^\n\r\[\]]+)", part, re.IGNORECASE)
        if p_match:
            contractor = re.sub(r"\[.*?\]|\(.*?\)", "", p_match.group(1)).strip()[:256]
        if not contractor:
            g_match = re.search(r"Генподрядчик\s*[:\s]*([^\n\r\[\]]+)", part, re.IGNORECASE)
            if g_match:
                contractor = re.sub(r"\[.*?\]|\(.*?\)", "", g_match.group(1)).strip()[:256]
        investor = ""
        i_match = re.search(r"Инвестор\s*[:\s]*([^\n\r\[\]]+)", part, re.IGNORECASE)
        if i_match:
            investor = re.sub(r"\[.*?\]|\(.*?\)", "", i_match.group(1)).strip()[:256]
        budget_val = None
        b_match = re.search(
            r"(?:Бюджет|Сумма|Стоимость|Инвестиции|Оценка)\s*[:\s]*([\d\s.,]+)\s*[млрдмлнтыс.]*\s*₽?",
            part,
            re.IGNORECASE,
        )
        if b_match:
            num_str = b_match.group(1).replace(" ", "").replace(",", ".")
            try:
                budget_val = float(re.search(r"[\d.]+", num_str).group(0))
            except (ValueError, AttributeError):
                pass
        if not budget_val:
            b2 = re.search(r"([\d\s.,]+)\s*(?:млрд|млн|тыс\.?)\s*руб", part, re.I)
            if b2:
                try:
                    budget_val = float(re.search(r"[\d.]+", b2.group(1).replace(" ", "").replace(",", ".")).group(0))
                except (ValueError, AttributeError):
                    pass
        if name or customer or contractor or investor or budget_val:
            blocks.append({
                "name": (name[:512] if name else "Проект"),
                "customer_name": customer or None,
                "contractor_name": contractor or None,
                "investor_name": investor or None,
                "budget": budget_val,
            })
    # Гибкий проход по ключевым словам из config
    keywords = _get_parsing_keywords()
    flexible = _extract_project_blocks_flexible(text, keywords)
    seen = {(b.get("name") or "").lower().strip()[:200] for b in blocks}
    for b in flexible:
        key = (b.get("name") or "").lower().strip()[:200]
        if key and key not in seen:
            seen.add(key)
            blocks.append(b)
    return blocks


async def _ingest_tenders_from_page_text(
    session: AsyncSession,
    text: str,
    page_url: str,
    existing_tender_ids: set[str],
) -> int:
    """По тексту страницы (любого источника) создать записи Tender в БД.

    :param session: Сессия БД.
    :param text: Текст страницы.
    :param page_url: URL страницы-источника.
    :param existing_tender_ids: Множество уже существующих tender_id.
    :return: Количество созданных тендеров.
    """
    blocks = _extract_tender_blocks_from_text(text)
    # Неуспех парсера: ничего не нашёл или мало блоков — дополняем через LLM
    if len(blocks) <= MAX_BLOCKS_TO_TRIGGER_LLM and len((text or "").strip()) >= MIN_TEXT_LEN_FOR_LLM:
        try:
            llm_blocks = await extract_tender_blocks_llm(text, max_chars=7000)
            seen = {(b.get("title") or "").lower().strip()[:200] for b in blocks}
            for b in llm_blocks:
                key = (b.get("title") or "").lower().strip()[:200]
                if key and key not in seen:
                    seen.add(key)
                    blocks.append(b)
        except Exception as exc:
            logger.warning("LLM tender extraction skipped (парсер дополнение): %s", exc)
    created = 0
    for block in blocks:
        title = (block.get("title") or "").strip() or "Тендер"
        context_text = f"{title}\n{page_url}\n{text or ''}"
        if not _is_construction_related(context_text):
            logger.info("Tender skipped by construction thematic filter: %s", title[:120])
            continue
        tender_id_raw = f"{page_url}|{title}"
        tender_id = hashlib.sha1(tender_id_raw.encode("utf-8")).hexdigest()[:20]
        if tender_id in existing_tender_ids:
            continue
        existing = await session.execute(select(Tender).where(Tender.tender_id == tender_id))
        if existing.scalars().first():
            existing_tender_ids.add(tender_id)
            continue
        tender = Tender(
            tender_id=tender_id,
            title=title[:512],
            source_url=page_url,
            winner=block.get("winner"),
            budget=block.get("budget"),
            status=block.get("status"),
            quality_flag=True,
        )
        session.add(tender)
        existing_tender_ids.add(tender_id)
        created += 1
        logger.info("Tender from source page: %s", title[:80])
    return created


async def _ingest_projects_from_page_text(
    session: AsyncSession,
    text: str,
    page_url: str,
    existing_project_keys: set[str],
) -> int:
    """По тексту страницы создать записи Project (коммерческие и государственные) в БД.

    :param session: Сессия БД.
    :param text: Текст страницы.
    :param page_url: URL страницы-источника.
    :param existing_project_keys: Множество уже существующих normalized_name.
    :return: Количество созданных проектов.
    """
    blocks = _extract_project_blocks_from_text(text)
    # Неуспех парсера: ничего не нашёл или мало блоков — дополняем через LLM
    if len(blocks) <= MAX_BLOCKS_TO_TRIGGER_LLM and len((text or "").strip()) >= MIN_TEXT_LEN_FOR_LLM:
        try:
            llm_blocks = await extract_project_blocks_llm(text, max_chars=7000)
            seen = {(b.get("name") or "").lower().strip()[:200] for b in blocks}
            for b in llm_blocks:
                key = (b.get("name") or "").lower().strip()[:200]
                if key and key not in seen:
                    seen.add(key)
                    blocks.append(b)
        except Exception as exc:
            logger.warning("LLM project extraction skipped (парсер дополнение): %s", exc)
    created = 0
    for block in blocks:
        name = (block.get("name") or "").strip() or "Проект"
        context_text = f"{name}\n{page_url}\n{text or ''}"
        if not _is_construction_related(context_text):
            logger.info("Project skipped by construction thematic filter: %s", name[:120])
            continue
        normalized_key = _normalize_project_key(name)
        if not normalized_key or normalized_key in existing_project_keys:
            continue
        existing = await session.execute(
            select(Project).where(Project.normalized_name == normalized_key)
        )
        if existing.scalars().first():
            existing_project_keys.add(normalized_key)
            continue
        project = Project(
            name=name[:256],
            normalized_name=normalized_key,
            customer_name=block.get("customer_name"),
            contractor_name=block.get("contractor_name"),
            investor_name=block.get("investor_name"),
            budget=block.get("budget"),
            source_urls=[page_url] if page_url else None,
        )
        session.add(project)
        existing_project_keys.add(normalized_key)
        created += 1
        logger.info("Project from source page: %s", name[:80])
    return created


async def ingest_sources(session: AsyncSession) -> int:
    """Собрать статьи из всех источников.

    Ограничений по last_checked_at нет: источники парсятся каждый проход, а дубли статей/тендеров/
    проектов отсекаются по Article.url, Tender.tender_id и Project.normalized_name.
    """
    try:
        result = await session.execute(
            select(Source)
            .order_by(nulls_first(asc(Source.last_checked_at)))
            .limit(MAX_SOURCES_PER_CYCLE)
        )
        sources = list(result.scalars().all())
    except Exception as e:
        logger.exception("ingest_sources: не удалось выбрать источники из БД: %s", e)
        raise
    logger.info("ingest_sources: источников к парсингу (все): %s", len(sources))
    if not sources:
        logger.info("ingest_sources: в БД нет источников")
        return 0
    client = HttpClient()
    processed = 0
    existing_tender_ids: set[str] = set()
    tenders_result = await session.execute(select(Tender.tender_id))
    existing_tender_ids.update(row[0] for row in tenders_result.all())
    known_source_urls: set[str] = set()
    urls_result = await session.execute(select(Source.url))
    known_source_urls.update(row[0] for row in urls_result.all() if row[0])
    existing_project_keys: set[str] = set()
    proj_result = await session.execute(select(Project.normalized_name))
    existing_project_keys.update(row[0] for row in proj_result.all() if row[0])

    async def _safe_get_text(url: str, source: Source) -> str | None:
        try:
            return await client.get_text(url)
        except httpx.HTTPStatusError as exc:
            logger.warning("Источник %s вернул %s для %s (источник не отключаем, повторим в следующем цикле)", source.url, exc.response.status_code, url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Ошибка HTTP для %s: %s", url, exc)
            return None

    async def _safe_get_bytes(url: str, source: Source) -> bytes | None:
        try:
            return await client.get_bytes(url)
        except httpx.HTTPStatusError as exc:
            logger.warning("Источник %s вернул %s для %s (источник не отключаем, повторим в следующем цикле)", source.url, exc.response.status_code, url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Ошибка HTTP для %s: %s", url, exc)
            return None

    def _base_url_from(url: str) -> str:
        from urllib.parse import urlparse
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}/" if p.netloc else url

    async def _discover_and_save_feeds(html: str, page_url: str) -> None:
        """Обнаружить RSS/Atom/XML в HTML и добавить новые источники в БД."""
        base = _base_url_from(page_url)
        for feed in discover_feeds_from_html(html, base):
            feed_url = feed.get("url") or ""
            if not feed_url or feed_url in known_source_urls:
                continue
            kind = "rss" if feed.get("kind") in ("rss", "atom", "xml") else "rss"
            name = feed.get("title") or feed_url
            if len(name) > 256:
                name = feed_url
            try:
                session.add(
                    Source(
                        name=name[:256],
                        url=feed_url,
                        kind=kind,
                        status="active",
                        auto_discovered=True,
                    )
                )
                await session.commit()
                known_source_urls.add(feed_url)
                logger.info("New feed source added: %s", feed_url)
            except IntegrityError:
                await session.rollback()
                known_source_urls.add(feed_url)
            except Exception as e:
                await session.rollback()
                logger.warning("Skip invalid feed %s: %s", feed_url, e)

    async def _get_text_from_page(html: str, page_url: str, source: Source) -> str:
        """Текст из HTML; при коротком ответе (JS-страница) — fallback: страница → PDF → парсинг."""
        text = extract_text(html)
        if text and len(text.strip()) >= 300:
            return text
        pdf_bytes = await fetch_page_as_pdf_async(page_url)
        if pdf_bytes:
            text_from_pdf = extract_text_from_pdf(pdf_bytes)
            if text_from_pdf and len(text_from_pdf.strip()) > len(text or ""):
                logger.info("Used PDF fallback for %s", page_url)
                return text_from_pdf
        return text or ""

    for source in sources:
        if processed >= MAX_ARTICLES_PER_CYCLE:
            logger.info("ingest_sources: достигнут лимит статей %s, выходим", MAX_ARTICLES_PER_CYCLE)
            break
        try:
            if source.kind == "rss":
                xml = await _safe_get_text(source.url, source)
                if not xml:
                    source.last_checked_at = _now_msk_naive()
                    await session.commit()
                    continue
                items = parse_feed_content(xml)
                if not items:
                    logger.debug("ingest_sources: источник %s (rss) — пустая лента", source.url)
                for item in items:
                    if processed >= MAX_ARTICLES_PER_CYCLE:
                        break
                    url = item.get("url") or ""
                    title = item.get("title")
                    published_at = None
                    published_raw = item.get("published_at")
                    if published_raw:
                        try:
                            published_at = parser.parse(published_raw)
                        except (TypeError, ValueError):
                            published_at = None
                    if url:
                        if url.lower().endswith(".pdf"):
                            data = await _safe_get_bytes(url, source)
                            if not data:
                                continue
                            text = extract_text_from_pdf(data)
                        else:
                            html = await _safe_get_text(url, source)
                            if not html:
                                continue
                            await _discover_and_save_feeds(html, url)
                            text = await _get_text_from_page(html, url, source)
                        await _save_article(session, source, url, title, published_at, text)
                        processed += 1
                        if text:
                            created_t = await _ingest_tenders_from_page_text(
                                session, text, url, existing_tender_ids
                            )
                            created_p = await _ingest_projects_from_page_text(
                                session, text, url, existing_project_keys
                            )
                            if created_t or created_p:
                                await session.commit()
            elif source.kind == "sitemap":
                xml = await _safe_get_text(source.url, source)
                if not xml:
                    source.last_checked_at = _now_msk_naive()
                    await session.commit()
                    continue
                urls = parse_sitemap(xml)
                for url in urls:
                    if processed >= MAX_ARTICLES_PER_CYCLE:
                        break
                    if url.lower().endswith(".pdf"):
                        data = await _safe_get_bytes(url, source)
                        if not data:
                            continue
                        text = extract_text_from_pdf(data)
                    else:
                        html = await _safe_get_text(url, source)
                        if not html:
                            continue
                        await _discover_and_save_feeds(html, url)
                        text = await _get_text_from_page(html, url, source)
                    await _save_article(session, source, url, None, None, text)
                    processed += 1
                    if text:
                        created_t = await _ingest_tenders_from_page_text(
                            session, text, url, existing_tender_ids
                        )
                        created_p = await _ingest_projects_from_page_text(
                            session, text, url, existing_project_keys
                        )
                        if created_t or created_p:
                            await session.commit()
            else:
                if source.url.lower().endswith(".pdf") or source.kind == "pdf":
                    data = await _safe_get_bytes(source.url, source)
                    if not data:
                        source.last_checked_at = _now_msk_naive()
                        await session.commit()
                        continue
                    text = extract_text_from_pdf(data)
                else:
                    html = await _safe_get_text(source.url, source)
                    if not html:
                        source.last_checked_at = _now_msk_naive()
                        await session.commit()
                        continue
                    await _discover_and_save_feeds(html, source.url)
                    text = await _get_text_from_page(html, source.url, source)
                # Главная страница источника
                await _save_article(session, source, source.url, source.name, None, text)
                processed += 1
                if text:
                    created_t = await _ingest_tenders_from_page_text(
                        session, text, source.url, existing_tender_ids
                    )
                    created_p = await _ingest_projects_from_page_text(
                        session, text, source.url, existing_project_keys
                    )
                    if created_t or created_p:
                        await session.commit()
                # Глубокий обход внутренних ссылок и sitemap для HTML-источников
                try:
                    internal_urls = await collect_internal_links(
                        source.url, client, max_pages=100, max_depth=2
                    )
                    logger.info(
                        "ingest_sources: deep crawl for %s, internal_urls=%s",
                        source.url,
                        len(internal_urls),
                    )
                    for url in internal_urls:
                        if processed >= MAX_ARTICLES_PER_CYCLE:
                            break
                        if url.lower().endswith(".pdf"):
                            data = await _safe_get_bytes(url, source)
                            if not data:
                                continue
                            page_text = extract_text_from_pdf(data)
                        else:
                            html2 = await _safe_get_text(url, source)
                            if not html2:
                                continue
                            await _discover_and_save_feeds(html2, url)
                            page_text = await _get_text_from_page(html2, url, source)
                        await _save_article(session, source, url, None, None, page_text)
                        processed += 1
                        if page_text:
                            created_t = await _ingest_tenders_from_page_text(
                                session, page_text, url, existing_tender_ids
                            )
                            created_p = await _ingest_projects_from_page_text(
                                session, page_text, url, existing_project_keys
                            )
                            if created_t or created_p:
                                await session.commit()
                except Exception as deep_exc:  # noqa: BLE001
                    logger.warning(
                        "ingest_sources: deep crawl failed for %s: %s", source.url, deep_exc
                    )
            source.last_checked_at = _now_msk_naive()
            await session.commit()
        except Exception as e:
            logger.exception(
                "ingest_sources: ошибка при обработке источника %s (%s): %s",
                getattr(source, "url", "?"),
                getattr(source, "kind", "?"),
                e,
            )

    logger.info("ingest_sources: завершено, обработано статей: %s", processed)
    return processed


async def _canonicalize_titles(
    session: AsyncSession, titles: list[str]
) -> dict[str, str]:
    """Получить канонические названия проектов с кэшем в БД."""

    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return {}

    cached_rows = await session.execute(
        select(ProjectTitleCache).where(ProjectTitleCache.original_title.in_(unique_titles))
    )
    cached = {row.original_title: row.canonical_title for row in cached_rows.scalars().all()}
    missing = [t for t in unique_titles if t not in cached]
    if not missing:
        return cached

    # Запускаем батчами, чтобы не перегружать LLM.
    batch_size = 20
    for idx in range(0, len(missing), batch_size):
        batch = missing[idx : idx + batch_size]
        try:
            mapping = await normalize_project_titles(batch)
        except Exception:  # noqa: BLE001
            mapping = {}
        for original in batch:
            canonical = mapping.get(original, "").strip() or original
            cached[original] = canonical
            session.add(
                ProjectTitleCache(
                    original_title=original,
                    canonical_title=canonical,
                )
            )
    await session.commit()
    return cached


async def ingest_perplexity_leads(
    session: AsyncSession,
    *,
    max_results: int = 1000,
) -> dict[str, int]:
    """Поиск информации о проектах, тендерах и госзаказах через Perplexity и запись в БД.

    Perplexity ищет по запросам (ключевые слова + госзакупки/44-ФЗ/223-ФЗ), возвращает ссылки
    на статьи и страницы; по ним парсим текст и извлекаем тендеры/проекты. Так поиск напрямую
    подключён к сбору данных о проектах, тендерах и госзаказах.
    """

    client = PerplexityClient()
    http_client = HttpClient()
    queries = await _build_perplexity_queries(session)
    existing_urls = set()
    existing_tender_ids = set()
    existing_project_keys = set()
    tenders = await session.execute(select(Tender.tender_id, Tender.source_url))
    for tender_id, source_url in tenders.all():
        if tender_id:
            existing_tender_ids.add(tender_id)
        if source_url:
            existing_urls.add(source_url)
    articles = await session.execute(select(Article.url))
    for (url,) in articles.all():
        if url:
            existing_urls.add(url)
    projects = await session.execute(select(Project.normalized_name))
    for (key,) in projects.all():
        if key:
            existing_project_keys.add(key)
    # Уже известные источники, чтобы не создавать дублей Source из лидов Perplexity
    known_source_urls: set[str] = set()
    sources_result = await session.execute(select(Source.url))
    for (src_url,) in sources_result.all():
        if src_url:
            known_source_urls.add(src_url)
    seen_urls: set[str] = set()
    created_projects = 0
    created_tenders = 0
    total_results = 0
    seen_project_keys: set[str] = set(existing_project_keys)

    async def _safe_fetch_text(url: str) -> str | None:
        try:
            if url.lower().endswith(".pdf"):
                data = await http_client.get_bytes(url)
                return extract_text_from_pdf(data)
            html = await http_client.get_text(url)
            return extract_text(html)
        except httpx.HTTPStatusError as exc:
            logger.warning("Perplexity источник %s вернул %s", url, exc.response.status_code)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Perplexity источник HTTP ошибка %s: %s", url, exc)
            return None

    def _entities_from_article(article: Article | None) -> ExtractedEntities | None:
        if not article or not article.entities:
            return None
        data = article.entities or {}
        return ExtractedEntities(
            projects=list((data.get("projects") or [])),
            companies=list((data.get("companies") or [])),
            persons=list((data.get("persons") or [])),
            emails=list((data.get("emails") or [])),
            phones=list((data.get("phones") or [])),
            money=list((data.get("money") or [])),
            dates=list((data.get("dates") or [])),
            winners=list((data.get("winners") or [])),
            applicants=list((data.get("applicants") or [])),
            contractors=list((data.get("contractors") or [])),
            subcontractors=list((data.get("subcontractors") or [])),
            customers=list((data.get("customers") or [])),
            investors=list((data.get("investors") or [])),
        )

    for query in queries:
        logger.info("Perplexity leads query: %s", query)
        results = await client.search_web(
            query,
            max_results=max_results,
            search_language_filter=["ru"],
            country="RU",
            search_recency_filter="year",
        )
        logger.info("Perplexity leads results: %s", len(results))
        total_results += len(results)
        titles = [(item.get("title") or "").strip() for item in results]
        canonical_map = await _canonicalize_titles(session, titles)
        noise_titles = await _filter_noise_titles_llm(titles)
        non_empty_titles = [t for t in titles if t]
        if non_empty_titles and len(noise_titles) >= len(non_empty_titles):
            logger.warning(
                "Perplexity leads: all titles marked noise, ignoring noise filter"
            )
            noise_titles = set()
        logger.info(
            "Perplexity leads: results=%s titles=%s noise=%s",
            len(results),
            len(non_empty_titles),
            len(noise_titles),
        )
        for item in results:
            try:
                url = item.get("url") or ""
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                if url and url in existing_urls:
                    continue
                # Добавляем новый Source для URL от Perplexity, если такого ещё нет
                if url and url not in known_source_urls:
                    try:
                        normalized_src = _normalize_source_url(url)
                        if normalized_src not in known_source_urls:
                            session.add(
                                Source(
                                    name=(item.get("title") or normalized_src)[:256],
                                    url=normalized_src,
                                    kind="html",
                                    status="active",
                                    auto_discovered=True,
                                )
                            )
                            await session.commit()
                            known_source_urls.add(normalized_src)
                            logger.info("Perplexity discover source added: %s", normalized_src)
                    except Exception as src_exc:  # noqa: BLE001
                        await session.rollback()
                        logger.warning("Perplexity discover source failed for %s: %s", url, src_exc)
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                if not title:
                    if snippet:
                        title = snippet[:180].rstrip()
                        logger.info("Lead missing title, derived from snippet: %s", title)
                    elif url:
                        title = url
                        logger.info("Lead missing title, derived from url: %s", title)
                    else:
                        logger.info("Lead skipped: empty title and snippet")
                        continue
                if title in noise_titles:
                    logger.info("Lead skipped: noise title=%s", title)
                    continue
                logger.info("Perplexity lead item: url=%s title=%s", url, title)
                full_text = await _safe_fetch_text(url) if url else None
                article = None
                if full_text:
                    logger.info("Perplexity parse source: %s", url)
                    article = await _save_article(session, None, url, title or None, None, full_text)
                text_blob = (full_text or f"{title}. {snippet}").strip()
                if not _is_construction_related(f"{title}\n{snippet}\n{text_blob}"):
                    logger.info("Lead skipped by construction thematic filter: %s", title[:120])
                    continue
                logger.info(
                    "Lead classify: url=%s has_full_text=%s text_len=%s",
                    url,
                    bool(full_text),
                    len(text_blob),
                )
                label = article.label if article and article.label else await classify_text(text_blob)
                logger.info("Lead label: url=%s label=%s", url, label)
                entities = _entities_from_article(article) or await extract_entities(text_blob)
                role_selection = await select_primary_roles(text_blob, entities)
                logger.info(
                    "Lead roles: url=%s customer=%s contractor=%s candidates=%s",
                    url,
                    role_selection.get("customer"),
                    role_selection.get("contractor"),
                    len(role_selection.get("candidates") or []),
                )
                company_candidates = role_selection.get("candidates") or []
                if not company_candidates and entities.companies:
                    company_candidates = entities.companies
                if label == "tender":
                    tender_id_raw = url or title
                    tender_id = hashlib.sha1(tender_id_raw.encode("utf-8")).hexdigest()[:20]
                    if tender_id in existing_tender_ids:
                        continue
                    existing = await session.execute(
                        select(Tender).where(Tender.tender_id == tender_id)
                    )
                    if existing.scalars().first():
                        continue
                    tender = Tender(
                        tender_id=tender_id,
                        title=title,
                        source_url=url or None,
                        quality_flag=True,
                    )
                    tender.customer = role_selection.get("customer")
                    tender.winner = role_selection.get("winner")
                    tender.contacts = {
                        "emails": entities.emails,
                        "phones": entities.phones,
                        "companies": entities.companies,
                        "customers": entities.customers,
                        "contractors": entities.contractors,
                        "winners": entities.winners,
                    }
                    session.add(tender)
                    created_tenders += 1
                    for role_name in [tender.customer, tender.winner] + list(company_candidates):
                        if not role_name:
                            continue
                        try:
                            profile = await enrich_company(session, name=role_name)
                            if profile.get("email"):
                                emails_list = tender.contacts.setdefault("emails", [])
                                if profile["email"] not in emails_list:
                                    emails_list.append(profile["email"])
                            if profile.get("phone"):
                                phones_list = tender.contacts.setdefault("phones", [])
                                if profile["phone"] not in phones_list:
                                    phones_list.append(profile["phone"])
                            if profile.get("sources"):
                                tender.contacts.setdefault("sources", []).extend(profile["sources"])
                        except Exception as enc:  # noqa: BLE001
                            logger.warning("Tender enrich_company skip %s: %s", role_name, enc)
                else:
                    canonical_name = canonical_map.get(title, title)
                    normalized_key = _normalize_project_key(canonical_name)
                    if normalized_key in existing_project_keys:
                        continue
                    existing = await session.execute(
                        select(Project).where(Project.normalized_name == normalized_key)
                    )
                    project = existing.scalars().first()
                    if project:
                        continue
                    project = Project(name=canonical_name, normalized_name=normalized_key)
                    project.customer_name = role_selection.get("customer")
                    project.contractor_name = role_selection.get("contractor")
                    project.investor_name = role_selection.get("investor")
                    project.customer_email = (entities.emails[0] if entities.emails else None)
                    project.customer_phone = (entities.phones[0] if entities.phones else None)
                    if url:
                        project.source_urls = [url]
                    session.add(project)
                    created_projects += 1
                    seen_project_keys.add(normalized_key)
                    logger.info("Project created: %s", project.name)
                    try:
                        if not project.description:
                            project.description = await summarize_project(
                                project.name,
                                text_blob,
                            )
                    except Exception as sum_exc:  # noqa: BLE001
                        logger.warning("Project summarize skip: %s", sum_exc)
                    role_names = [
                        project.customer_name,
                        project.contractor_name,
                        project.investor_name,
                    ]
                    for role_name in [name for name in role_names if name] + list(company_candidates):
                        try:
                            profile = await enrich_company(session, name=role_name)
                            if profile.get("email") and not project.customer_email:
                                project.customer_email = profile["email"]
                            if profile.get("phone") and not project.customer_phone:
                                project.customer_phone = profile["phone"]
                        except Exception as enc:  # noqa: BLE001
                            logger.warning("Project enrich_company skip %s: %s", role_name, enc)
            except Exception as lead_exc:  # noqa: BLE001
                logger.warning(
                    "Perplexity lead failed (skipping, will commit rest): url=%s error=%s",
                    item.get("url"),
                    lead_exc,
                    exc_info=True,
                )
                continue

    try:
        await session.commit()
    except Exception as commit_exc:  # noqa: BLE001
        logger.error("Perplexity leads commit failed: %s", commit_exc, exc_info=True)
        raise
    return {
        "projects": created_projects,
        "tenders": created_tenders,
        "total_results": total_results,
    }


async def enrich_projects_missing(session: AsyncSession, *, limit: int = 200) -> dict[str, int]:
    """Дозаполнить проекты с пустыми полями через GPT+Perplexity+Dadata."""

    stmt = (
        select(Project)
        .where(
            or_(
                Project.description.is_(None),
                Project.customer_name.is_(None),
                Project.contractor_name.is_(None),
                Project.customer_email.is_(None),
                Project.customer_phone.is_(None),
            )
        )
        .limit(limit)
    )
    projects = (await session.execute(stmt)).scalars().all()
    if not projects:
        return {"updated": 0}

    client = PerplexityClient()
    updated = 0
    for project in projects:
        logger.info("Auto-enrich project: id=%s name=%s", project.id, project.name)
        query = f"{project.name} заказчик подрядчик исполнитель контакты Россия РФ"
        results = await client.search_web(
            query,
            max_results=5,
            search_language_filter=["ru"],
            country="RU",
            search_recency_filter="year",
        )
        logger.info("Auto-enrich results: id=%s count=%s", project.id, len(results))
        rusprofile_query = f"{project.name} site:rusprofile.ru"
        rusprofile_results = await client.search_web(
            rusprofile_query,
            max_results=5,
            search_domain_filter=["rusprofile.ru"],
            search_language_filter=["ru"],
            country="RU",
            search_recency_filter="year",
        )
        logger.info(
            "Auto-enrich rusprofile: id=%s count=%s", project.id, len(rusprofile_results)
        )
        snippets = [
            f"{item.get('title')}\n{item.get('snippet')}\n{item.get('url')}"
            for item in results
            if item.get("title") or item.get("snippet") or item.get("url")
        ]
        rusprofile_snippets = [
            f"{item.get('title')}\n{item.get('snippet')}\n{item.get('url')}"
            for item in rusprofile_results
            if item.get("title") or item.get("snippet") or item.get("url")
        ]
        text_blob = "\n\n".join(snippets + rusprofile_snippets).strip()
        if not text_blob:
            text_blob = project.name
        entities = await extract_entities(text_blob)
        role_selection = await select_primary_roles(text_blob, entities)
        logger.info(
            "Auto-enrich roles: id=%s customer=%s contractor=%s candidates=%s",
            project.id,
            role_selection.get("customer"),
            role_selection.get("contractor"),
            len(role_selection.get("candidates") or []),
        )
        if not project.description:
            project.description = await summarize_project(project.name, text_blob)
        project.customer_name = project.customer_name or role_selection.get("customer")
        project.contractor_name = project.contractor_name or role_selection.get("contractor")
        project.investor_name = project.investor_name or role_selection.get("investor")
        project.customer_email = project.customer_email or (entities.emails[0] if entities.emails else None)
        project.customer_phone = project.customer_phone or (entities.phones[0] if entities.phones else None)
        if rusprofile_snippets:
            contacts = await extract_contacts_from_snippets(rusprofile_snippets)
            logger.info(
                "Auto-enrich contacts: id=%s email=%s phone=%s",
                project.id,
                bool(contacts.get("email")),
                bool(contacts.get("phone")),
            )
            project.customer_email = project.customer_email or contacts.get("email")
            project.customer_phone = project.customer_phone or contacts.get("phone")
        for url in [item.get("url") for item in results if item.get("url")]:
            if not project.source_urls:
                project.source_urls = []
            if url not in project.source_urls:
                project.source_urls.append(url)
        for url in [item.get("url") for item in rusprofile_results if item.get("url")]:
            if not project.source_urls:
                project.source_urls = []
            if url not in project.source_urls:
                project.source_urls.append(url)
        candidates = role_selection.get("candidates") or []
        if not candidates and entities.companies:
            candidates = [entities.companies[0]]
        for role_name in candidates:
            if not role_name:
                continue
            profile = await enrich_company(session, name=role_name)
            logger.info(
                "Dadata enrich: id=%s company=%s email=%s phone=%s",
                project.id,
                role_name,
                bool(profile.get("email")),
                bool(profile.get("phone")),
            )
            if profile.get("email") and not project.customer_email:
                project.customer_email = profile["email"]
            if profile.get("phone") and not project.customer_phone:
                project.customer_phone = profile["phone"]
        updated += 1

    await session.commit()
    return {"updated": updated}


async def _build_perplexity_queries(session: AsyncSession) -> list[str]:
    """Сформировать поисковые запросы из наборов ключевых слов/конфига."""

    await bootstrap_keyword_sets_from_yaml(session)
    keywords: list[str] = []
    result = await session.execute(
        select(SearchKeywordSet).options(selectinload(SearchKeywordSet.keywords))
    )
    for keyword_set in result.scalars().all():
        for item in keyword_set.keywords:
            if item.text:
                keywords.append(item.text.strip())
    if not keywords:
        cfg = load_keywords_config()
        keywords = cfg.get("construction_keywords", []) or []
    keywords = [kw for kw in keywords if kw]
    if not keywords:
        return [
            "строительные тендеры и закупки 2025 2026 Россия актуальные",
            "строительные проекты и инвестиции 2025 2026 Россия актуальные",
        ]

    async def _expand_queries_llm(seed_keywords: list[str]) -> list[str]:
        client = OpenAIClient()
        system = (
            "ВНИМАТЕЛЬНО ПРОАНАЛИЗИРУЙ, как улучшить запрос для максимально точного поиска. "
            "Цель — узнавать о новых проектах, тендерах и госзаказах (44-ФЗ, 223-ФЗ, ЕИС, госзакупки РФ), "
            "находить контакты заказчиков и подрядчиков. "
            "Формируй запросы для поиска КОНКРЕТНОЙ ИНФОРМАЦИИ: журналы, СМИ, порталы закупок — "
            "статьи и страницы с описанием проектов/тендеров/госзаказов и контактами. "
            "Расширяй примитивные фразы. Добавляй: заказчик/подрядчик/победитель, контакты (телефон, email), "
            "2025/2026, РФ/Россия, тендеры/закупки/проекты/госзаказы/госзакупки/СМИ/журнал/портал. "
            "Исключай Казахстан. Запросы на русском, без булевых операторов и кавычек. "
            "Верни ТОЛЬКО JSON‑массив строк."
        )
        user_content = (
            "Примитивные фразы (JSON‑массив строк):\n"
            f"{json.dumps(seed_keywords, ensure_ascii=False)}\n\n"
            "Верни JSON‑массив из 10–20 расширенных поисковых запросов."
        )
        try:
            response = await client.chat(
                system,
                [{"role": "user", "content": user_content}],
            )
            content = response.get("content") or []
            text_blocks = [b.get("text") for b in content if b.get("type") == "text"]
            merged = "\n".join(t for t in text_blocks if t)
            expanded = json.loads(merged)
            if isinstance(expanded, list):
                return [str(item).strip() for item in expanded if str(item).strip()]
        except Exception:
            return []
        return []
    expanded = await _expand_queries_llm(keywords)
    search_settings = get_search_settings()
    query_limit = int(search_settings.get("perplexity_query_limit", 0) or 0)
    if expanded:
        unique_queries: list[str] = []
        seen: set[str] = set()
        for q in expanded:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        if query_limit > 0:
            return unique_queries[:query_limit]
        return unique_queries[:20]

    # Fallback: поиск по проектам, тендерам, госзаказам и госзакупкам (СМИ, журналы, порталы)
    role_terms = "заказчик подрядчик исполнитель победитель контакты телефон email"
    country_terms = "Россия РФ"
    base = " ".join(keywords[:8]) if keywords else "строительство инфраструктура"
    fallback_queries = [
        f"{base} тендеры закупки строительство 2025 2026 актуальные СМИ журнал портал {role_terms} {country_terms}",
        f"{base} проекты инвестиции строительство 2025 2026 актуальные СМИ журнал портал {role_terms} {country_terms}",
        f"{base} госзаказы госзакупки 44-ФЗ 223-ФЗ ЕИС закупки РФ 2025 2026 {role_terms} {country_terms}",
        "госзаказы строительство реконструкция дороги мосты 2025 2026 Россия заказчик подрядчик",
        "госзакупки тендеры строительные работы капитальный ремонт Россия актуальные",
    ]
    if query_limit > 0:
        return fallback_queries[:query_limit]
    return fallback_queries


def _normalize_project_name(raw_name: str) -> str:
    """Нормализовать название проекта для записи.

    :param raw_name: Исходное название.
    :return: Нормализованное короткое название.
    """

    cleaned = " ".join(raw_name.replace("\n", " ").split()).strip()
    if len(cleaned) > 160:
        cleaned = cleaned[:160].rstrip(" ,.;:-")
    return cleaned


async def _filter_noise_titles_llm(titles: list[str]) -> set[str]:
    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return set()
    batch_size = 20
    noise: set[str] = set()
    for idx in range(0, len(unique_titles), batch_size):
        batch = unique_titles[idx : idx + batch_size]
        try:
            mapping = await classify_project_titles(batch)
        except Exception:  # noqa: BLE001
            mapping = {}
        for title in batch:
            if mapping.get(title) is True:
                noise.add(title)
    return noise


def _parse_ruble_amount(raw_value: str) -> float | None:
    """Распарсить сумму в рублях из строки.

    :param raw_value: Сырые данные суммы.
    :return: Сумма в рублях или None.
    """

    lowered = raw_value.lower().replace(" ", "")
    if any(token in lowered for token in ("usd", "дол", "$", "eur", "евро", "€")):
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


def _collect_ruble_amounts(text: str, money_values: list[str]) -> list[float]:
    """Собрать суммы в рублях из сущностей и текста.

    :param text: Полный текст статьи.
    :param money_values: Извлеченные сущности денег.
    :return: Список сумм в рублях.
    """

    amounts: list[float] = []
    for value in money_values:
        parsed = _parse_ruble_amount(str(value))
        if parsed:
            amounts.append(parsed)
    for match in re.finditer(
        r"\d+(?:[.,]\d+)?\s*(?:тыс|млн|млрд)?\s*руб",
        text.lower(),
    ):
        parsed = _parse_ruble_amount(match.group(0))
        if parsed:
            amounts.append(parsed)
    return amounts
def _normalize_project_key(raw_name: str) -> str:
    """Нормализовать ключ проекта для защиты от дублей.

    :param raw_name: Исходное название.
    :return: Нормализованный ключ.
    """

    lowered = raw_name.lower()
    cleaned = re.sub(r"[\"'«»]", "", lowered)
    cleaned = re.sub(r"[^a-zа-я0-9]+", " ", cleaned)
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens).strip()


def _normalize_company_key(raw_name: str) -> str:
    """Нормализовать ключ компании для защиты от дублей.

    :param raw_name: Исходное название.
    :return: Нормализованный ключ.
    """

    lowered = raw_name.lower()
    cleaned = re.sub(r"[\"'«»]", "", lowered)
    cleaned = cleaned.replace("общество с ограниченной ответственностью", "ооо")
    cleaned = cleaned.replace("акционерное общество", "ао")
    cleaned = cleaned.replace("публичное акционерное общество", "пао")
    cleaned = cleaned.replace("закрытое акционерное общество", "зао")
    cleaned = re.sub(r"[^a-zа-я0-9]+", " ", cleaned)
    return " ".join(cleaned.split()).strip()


def _normalize_phone(raw_phone: str) -> str | None:
    """Нормализовать телефон для дедупликации.

    :param raw_phone: Сырый телефон.
    :return: Нормализованный телефон или None.
    """

    digits = re.sub(r"\D+", "", raw_phone)
    if len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    if len(digits) == 10:
        digits = f"7{digits}"
    if len(digits) < 10:
        return None
    return f"+{digits}"


def _filter_contact_values(
    emails: list[str],
    phones: list[str],
    source_url: str,
) -> tuple[list[str], list[str]]:
    """Очистить контакты от мусорных доменов и привести телефоны.

    :param emails: Сырые email.
    :param phones: Сырые телефоны.
    :param source_url: URL статьи-источника.
    :return: Очищенные email и телефоны.
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
    domain = source_url.replace("https://", "").replace("http://", "").split("/")[0]
    domain = domain.replace("www.", "")
    clean_emails: list[str] = []
    for email in emails:
        email_lower = email.lower()
        if "@" not in email_lower:
            continue
        email_domain = email_lower.split("@")[-1]
        if email_domain in free_domains:
            continue
        if domain and email_domain.endswith(domain):
            continue
        if email_lower not in clean_emails:
            clean_emails.append(email_lower)
    clean_phones: list[str] = []
    for phone in phones:
        normalized = _normalize_phone(phone)
        if normalized and normalized not in clean_phones:
            clean_phones.append(normalized)
    return clean_emails, clean_phones


def _merge_contact_lists(existing: list[str], incoming: list[str]) -> list[str]:
    """Объединить списки контактов без дублей.

    :param existing: Текущие контакты.
    :param incoming: Новые контакты.
    :return: Объединенный список.
    """

    merged = list(existing)
    for item in incoming:
        if item and item not in merged:
            merged.append(item)
    return merged


def _filter_company_names(companies: list[str]) -> list[str]:
    """Нормализовать список компаний без эвристических фильтров."""

    cleaned_list: list[str] = []
    for name in companies:
        cleaned = " ".join(name.replace("\n", " ").split()).strip()
        if not cleaned:
            continue
        cleaned_list.append(cleaned)
    return cleaned_list


async def _upsert_projects(
    session: AsyncSession, projects: list[str], article: Article, text: str
) -> None:
    """Создать проекты по данным статьи.

    :param session: Асинхронная сессия БД.
    :param projects: Список упоминаний проектов.
    :param article: Статья-источник.
    :param text: Текст статьи.
    :return: None.
    """

    entities = article.entities or {}
    names = projects or ([article.title] if article.label == "project" and article.title else [])
    canonical_map = await _canonicalize_titles(session, names)
    noise_titles = await _filter_noise_titles_llm(names)
    for name in names:
        if name in noise_titles:
            continue
        cleaned = _normalize_project_name(canonical_map.get(name, name))
        if not cleaned:
            continue
        if len(cleaned) > 200:
            cleaned = cleaned[:200]
        normalized_key = _normalize_project_key(cleaned)
        with session.no_autoflush:
            existing = await session.execute(
                select(Project).where(Project.normalized_name == normalized_key)
            )
            project = existing.scalars().first()
        if not project:
            project = Project(name=cleaned, normalized_name=normalized_key)
            session.add(project)
        if not project.budget:
            money_values = article.entities.get("money", []) if article.entities else []
            amounts = _collect_ruble_amounts(text, money_values)
            if amounts:
                project.budget = max(amounts)
        if not project.start_date and article.entities:
            dates = article.entities.get("dates", []) or []
            if dates:
                try:
                    project.start_date = parser.parse(dates[0]).date()
                except (TypeError, ValueError):
                    pass
        if not project.end_date and article.entities:
            dates = article.entities.get("dates", []) or []
            if len(dates) > 1:
                try:
                    project.end_date = parser.parse(dates[-1]).date()
                except (TypeError, ValueError):
                    pass

        if not project.description:
            project.description = await summarize_project(project.name, text)

        extracted = ExtractedEntities(
            projects=list((entities.get("projects") or [])),
            companies=list((entities.get("companies") or [])),
            persons=list((entities.get("persons") or [])),
            emails=list((entities.get("emails") or [])),
            phones=list((entities.get("phones") or [])),
            money=list((entities.get("money") or [])),
            dates=list((entities.get("dates") or [])),
            winners=list((entities.get("winners") or [])),
            applicants=list((entities.get("applicants") or [])),
            contractors=list((entities.get("contractors") or [])),
            subcontractors=list((entities.get("subcontractors") or [])),
            customers=list((entities.get("customers") or [])),
            investors=list((entities.get("investors") or [])),
        )
        role_selection = await select_primary_roles(text, extracted)
        project.customer_name = project.customer_name or role_selection.get("customer")
        project.contractor_name = project.contractor_name or role_selection.get("contractor")
        project.investor_name = project.investor_name or role_selection.get("investor")
        project.customer_email = project.customer_email or (extracted.emails[0] if extracted.emails else None)
        project.customer_phone = project.customer_phone or (extracted.phones[0] if extracted.phones else None)
        for role_name in role_selection.get("candidates") or []:
            if not role_name:
                continue
            profile = await enrich_company(session, name=role_name)
            if profile.get("email") and not project.customer_email:
                project.customer_email = profile["email"]
            if profile.get("phone") and not project.customer_phone:
                project.customer_phone = profile["phone"]

        refs = project.source_urls or []
        if article.url and article.url not in refs:
            refs.append(article.url)
            project.source_urls = refs


async def _upsert_companies(
    session: AsyncSession,
    companies: list[str],
    emails: list[str],
    phones: list[str],
    source_url: str,
) -> None:
    """Создать компании по данным статьи.

    :param session: Асинхронная сессия БД.
    :param companies: Список компаний.
    :param emails: Найденные email.
    :param phones: Найденные телефоны.
    :param source_url: URL статьи-источника.
    :return: None.
    """

    filtered_emails, filtered_phones = _filter_contact_values(emails, phones, source_url)
    primary_email = filtered_emails[0] if filtered_emails else None
    primary_phone = filtered_phones[0] if filtered_phones else None
    for name in companies:
        cleaned = " ".join(name.replace("\n", " ").split()).strip()
        if not cleaned:
            continue
        if len(cleaned) > 200:
            continue
        if "главная" in cleaned.lower() and "архив" in cleaned.lower():
            continue
        normalized_key = _normalize_company_key(cleaned)
        with session.no_autoflush:
            existing = await session.execute(
                select(Company).where(Company.normalized_name == normalized_key)
            )
            company = existing.scalars().first()
        if not company:
            company = Company(name=cleaned, normalized_name=normalized_key)
            session.add(company)
        elif not company.normalized_name:
            company.normalized_name = normalized_key
        if primary_email and not company.email:
            company.email = primary_email
        if primary_phone and not company.phone:
            company.phone = primary_phone
        contacts = company.contacts or {}
        contacts_emails = contacts.get("emails", [])
        contacts_phones = contacts.get("phones", [])
        contacts["emails"] = _merge_contact_lists(contacts_emails, filtered_emails)
        contacts["phones"] = _merge_contact_lists(contacts_phones, filtered_phones)
        company.contacts = contacts
        refs = company.source_refs or []
        if source_url and source_url not in refs:
            refs.append(source_url)
            company.source_refs = refs

        # Автоматическое обогащение профиля компании через Dadata + Rusprofile.
        # Запускаем один раз при создании/первом заполнении, если у компании
        # ещё нет ИНН или адреса.
        if not company.inn or not company.address:
            profile = await enrich_company(
                session,
                inn=company.inn,
                email=company.email,
                phone=company.phone,
                name=company.name,
            )
            company.inn = company.inn or profile.get("inn")
            company.address = company.address or profile.get("address")
            if profile.get("email") and not company.email:
                company.email = profile["email"]
            if profile.get("phone") and not company.phone:
                company.phone = profile["phone"]
            # сохраняем источники обогащения в contacts.external_sources
            contacts = company.contacts or {}
            contacts["external_sources"] = profile.get("sources") or []
            company.contacts = contacts


async def match_tenders_and_articles(session: AsyncSession) -> int:
    """Сопоставить тендеры и статьи и сохранить связи.

    :param session: Асинхронная сессия БД.
    :return: Количество созданных связей.
    """

    settings = get_settings()
    tenders = (await session.execute(select(Tender))).scalars().all()
    articles = (await session.execute(select(Article))).scalars().all()
    created = 0

    for tender in tenders:
        if not tender.title:
            continue
        for article in articles:
            if not article.title:
                continue
            score = compute_confidence(tender.title, article.title, tender.region)
            if score < settings.matching_min_threshold:
                continue
            existing = await session.execute(
                select(MatchLink).where(
                    MatchLink.tender_id == tender.id, MatchLink.article_id == article.id
                )
            )
            if existing.scalars().first():
                continue
            link = MatchLink(
                tender_id=tender.id,
                article_id=article.id,
                confidence_score=score,
                approved=score >= settings.matching_threshold,
            )
            session.add(link)
            created += 1
    await session.commit()
    return created
