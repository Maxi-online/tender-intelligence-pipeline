"""Парсер sitemap XML.

Автор: Maxi-online
"""

from __future__ import annotations

from xml.etree import ElementTree


def parse_sitemap(xml_content: str) -> list[str]:
    """Извлечь список URL из sitemap.

    :param xml_content: XML содержимое sitemap.
    :return: Список URL страниц.
    """

    urls: list[str] = []
    tree = ElementTree.fromstring(xml_content)
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    for url_node in tree.findall(f"{namespace}url"):
        loc = url_node.find(f"{namespace}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls
