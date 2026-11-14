"""Parser RSS/Atom ribbons.

Author: Maxi-online
"""

from __future__ import annotations

import feedparser


def parse_feed_content(content: str) -> list[dict[str, str]]:
    """Unload RSS/Atom content and return elements.

    :param content: XML content RSS/Atom.
    :return: List of elements with title, reference and date.
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
    """Unload RSS/Atom tape and return the elements.

    :param feed_url: URL RSS/Atom tape.
    :return: List of elements with title, reference and date.
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
