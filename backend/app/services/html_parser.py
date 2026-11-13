"""Парсер HTML страниц.

Автор: Maxi-online
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    """Извлечь основной текст из HTML.

    :param html: HTML документ в виде строки.
    :return: Очищенный текст без тегов и скриптов.
    """

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return text
