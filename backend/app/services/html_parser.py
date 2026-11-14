"""HTML Parser pages.

Author: Maxi-online
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    """Extract the basic text from HTML.

    :param html: HTML document in string form.
    :return: Peeled text without tags and scripts.
    """

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return text
