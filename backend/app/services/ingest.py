"""Сбор и парсинг данных из источников.

Автор: Maxi-online
"""

from __future__ import annotations

from typing import Any

from app.services.http_client import HttpClient
from app.services.html_parser import extract_text
from app.services.rss_parser import parse_feed_content
from app.services.sitemap import parse_sitemap


async def ingest_rss(feed_url: str) -> list[dict[str, Any]]:
    """Собрать новости из RSS/Atom ленты.

    :param feed_url: URL RSS/Atom ленты.
    :return: Список элементов ленты.
    """

    client = HttpClient()
    xml = await client.get_text(feed_url)
    return parse_feed_content(xml)


async def ingest_html_page(url: str) -> dict[str, Any]:
    """Собрать текст со страницы HTML.

    :param url: URL страницы.
    :return: Словарь с URL и текстом страницы.
    """

    client = HttpClient()
    html = await client.get_text(url)
    text = extract_text(html)
    return {"url": url, "text": text}


async def ingest_sitemap(url: str) -> list[str]:
    """Собрать URL страниц из sitemap.

    :param url: URL sitemap.xml.
    :return: Список URL страниц.
    """

    client = HttpClient()
    xml_content = await client.get_text(url)
    return parse_sitemap(xml_content)
