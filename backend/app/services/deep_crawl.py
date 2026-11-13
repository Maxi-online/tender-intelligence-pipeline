"""Глубокий парсинг HTML-источников: обход внутренних ссылок и sitemap.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from collections import deque
from typing import List, Set, Tuple
from urllib.parse import urljoin, urlparse

import logging

from app.services.http_client import HttpClient
from app.services.sitemap import parse_sitemap

logger = logging.getLogger(__name__)


def _same_domain(base: str, url: str) -> bool:
    """Проверить, что URL относится к тому же домену, что и базовый."""

    try:
        pb = urlparse(base)
        pu = urlparse(url)
        return bool(pb.netloc and pu.netloc and pb.netloc == pu.netloc)
    except Exception:
        return False


async def collect_internal_links(
    start_url: str,
    client: HttpClient,
    *,
    max_pages: int = 100,
    max_depth: int = 2,
) -> List[str]:
    """Собрать внутренние ссылки для глубокого обхода домена.

    - Стартуем с start_url.
    - Пытаемся прочитать sitemap.xml и добавить ссылки оттуда.
    - Дальше обходим HTML-страницы, вытаскивая href и ограничивая глубину/количество.
    """

    visited: Set[str] = set()
    results: Set[str] = set()
    queue: deque[Tuple[str, int]] = deque()

    if not start_url:
        return []

    queue.append((start_url, 0))

    # Попробуем sitemap на том же домене
    try:
        parsed = urlparse(start_url)
        if parsed.scheme and parsed.netloc:
            sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            xml = await client.get_text(sitemap_url)
            if xml:
                sitemap_links = [u for u in parse_sitemap(xml) if _same_domain(start_url, u)]
                for u in sitemap_links:
                    queue.append((u, 0))
                logger.info("deep_crawl: %s sitemap urls=%s", start_url, len(sitemap_links))
    except Exception as exc:  # noqa: BLE001
        logger.warning("deep_crawl: sitemap failed for %s: %s", start_url, exc)

    pages_processed = 0

    while queue and pages_processed < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if depth > max_depth:
            continue
        if not _same_domain(start_url, url):
            continue

        try:
            html = await client.get_text(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("deep_crawl: HTTP error for %s: %s", url, exc)
            continue
        if not html:
            continue

        pages_processed += 1
        results.add(url)

        # Собираем href для дальнейшего обхода
        try:
            import re

            hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
            for href in hrefs:
                full = urljoin(url, href)
                if full not in visited and _same_domain(start_url, full):
                    queue.append((full, depth + 1))
        except Exception as exc:  # noqa: BLE001
            logger.warning("deep_crawl: link parse error for %s: %s", url, exc)

    logger.info(
        "deep_crawl: done for %s, pages_processed=%s, unique_urls=%s",
        start_url,
        pages_processed,
        len(results),
    )
    # Возвращаем список, чтобы порядок был детерминированным для последующей обработки
    return list(results)

