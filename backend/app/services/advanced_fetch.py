"""Продвинутые методы загрузки и парсинга: RSS/Atom/XML, страница → PDF.

Автор: Maxi-online
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def discover_feeds_from_html(html: str, base_url: str) -> list[dict]:
    """Обнаружить RSS, Atom и XML-каналы в HTML по стандарту link rel=\"alternate\".

    См. https://www.rssboard.org/rss-autodiscovery и https://indieweb.org/rel-feed
    :param html: Исходный HTML страницы.
    :param base_url: Базовый URL для разрешения относительных ссылок.
    :return: Список словарей [{\"url\": str, \"kind\": \"rss\"|\"atom\"|\"xml\", \"title\": str}].
    """
    if not html or not base_url:
        return []
    soup = BeautifulSoup(html, "lxml")
    feeds: list[dict] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("link", rel=True, href=True):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        rel_lower = [r.strip().lower() for r in rel]
        if "alternate" not in rel_lower:
            continue
        type_attr = (link.get("type") or "").strip().lower()
        href = (link.get("href") or "").strip()
        if not href:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        kind = None
        if "application/rss+xml" in type_attr or "application/rss" in type_attr:
            kind = "rss"
        elif "application/atom+xml" in type_attr or "application/atom" in type_attr:
            kind = "atom"
        elif "application/xml" in type_attr or "text/xml" in type_attr:
            kind = "xml"
        elif type_attr and ("rss" in type_attr or "atom" in type_attr or "xml" in type_attr):
            kind = "rss" if "rss" in type_attr else ("atom" if "atom" in type_attr else "xml")

        if not kind and (href.endswith(".rss") or href.endswith("/rss") or "/feed" in href.lower()):
            kind = "rss"
        if not kind and (".atom" in href or "/atom" in href):
            kind = "atom"
        if not kind:
            continue

        title = (link.get("title") or "").strip() or None
        seen_urls.add(full_url)
        feeds.append({"url": full_url, "kind": kind, "title": title})
        logger.info("Discovered feed: %s %s", kind, full_url)

    # Дополнительно: ссылки на типичные пути каналов
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        text = (a.get_text() or "").strip().lower()
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        if any(x in href.lower() for x in ["/feed", "/rss", "/atom", ".rss", ".xml"]) or (
            "rss" in text or "подписаться" in text or "feed" in text
        ):
            if full_url.startswith("http") and full_url != base_url:
                seen_urls.add(full_url)
                kind = "atom" if ".atom" in href else "rss"
                feeds.append({"url": full_url, "kind": kind, "title": None})

    return feeds


def fetch_page_as_pdf_sync(url: str, timeout_ms: int = 30000) -> bytes | None:
    """Сохранить страницу в PDF через headless-браузер (Playwright), затем вернуть байты PDF.

    Нестандартный метод для JS-тяжёлых страниц: рендер в браузере → PDF → парсинг.
    Если playwright не установлен, возвращает None.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("playwright not installed, skip PDF capture")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2000)
                pdf_bytes = page.pdf(format="A4", print_background=True)
                return pdf_bytes
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("PDF capture failed for %s: %s", url, exc)
        return None


async def fetch_page_as_pdf_async(url: str, timeout_ms: int = 30000) -> bytes | None:
    """Асинхронно сохранить страницу в PDF (Playwright). Если библиотеки нет — None."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.debug("playwright not installed, skip PDF capture")
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(2000)
                pdf_bytes = await page.pdf(format="A4", print_background=True)
                return pdf_bytes
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning("PDF capture failed for %s: %s", url, exc)
        return None
