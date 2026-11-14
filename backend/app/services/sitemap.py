"""Parser situamp XML.

Author: Maxi-online
"""

from __future__ import annotations

from xml.etree import ElementTree


def parse_sitemap(xml_content: str) -> list[str]:
    """Extract the URL list from the sitemap.

    :param xml_content: XML contents of siteap.
    :return: URL List.
    """

    urls: list[str] = []
    tree = ElementTree.fromstring(xml_content)
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    for url_node in tree.findall(f"{namespace}url"):
        loc = url_node.find(f"{namespace}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls
