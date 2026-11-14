"""Collection and parasing of data from sources.

Author: Maxi-online
"""

from __future__ import annotations

from typing import Any

from app.services.http_client import HttpClient
from app.services.html_parser import extract_text
from app.services.rss_parser import parse_feed_content
from app.services.sitemap import parse_sitemap


async def ingest_rss(feed_url: str) -> list[dict[str, Any]]:
    """Collect news from RSS/Atom ribbon.

    :param feed_url: URL RSS/Atom tape.
    :return: List of ribbon elements.
    """

    client = HttpClient()
    xml = await client.get_text(feed_url)
    return parse_feed_content(xml)


async def ingest_html_page(url: str) -> dict[str, Any]:
    """Collect text from the XML page.

    :param url: UrL pages.
    :return: Vocabulary with URL and page text.
    """

    client = HttpClient()
    html = await client.get_text(url)
    text = extract_text(html)
    return {"url": url, "text": text}


async def ingest_sitemap(url: str) -> list[str]:
    """Gather the URL pages from the siteup.

    :param url: URL sitemap.xml.
    :return: URL List.
    """

    client = HttpClient()
    xml_content = await client.get_text(url)
    return parse_sitemap(xml_content)
