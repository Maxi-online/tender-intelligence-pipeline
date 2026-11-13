"""Парсер RSS/Atom лент.

Автор: Maxi-online
"""

from __future__ import annotations

import feedparser


def parse_feed_content(content: str) -> list[dict[str, str]]:
    """Распарсить RSS/Atom контент и вернуть элементы.

    :param content: XML контент RSS/Atom.
    :return: Список элементов с заголовком, ссылкой и датой.
    """

    parsed = feedparser.parse(content)
    items: list[dict[str, str]] = []
    for entry in parsed.entries:
        published = getattr(entry, "published", None) or getattr(entry, "updated", "")
        items.append(
            {
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "published_at": str(published),
            }
        )
    return items


def parse_feed(feed_url: str) -> list[dict[str, str]]:
    """Распарсить RSS/Atom ленту и вернуть элементы.

    :param feed_url: URL RSS/Atom ленты.
    :return: Список элементов с заголовком, ссылкой и датой.
    """

    parsed = feedparser.parse(feed_url)
    items: list[dict[str, str]] = []
    for entry in parsed.entries:
        published = getattr(entry, "published", None) or getattr(entry, "updated", "")
        items.append(
            {
                "title": getattr(entry, "title", ""),
                "url": getattr(entry, "link", ""),
                "published_at": str(published),
            }
        )
    return items
