"""Сопоставление сущностей между источниками.

Автор: Maxi-online
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def _token_set_ratio(left: str, right: str) -> float:
    """Приближенный аналог token_set_ratio без внешних зависимостей."""

    tokens_left = set(re.findall(r"\w+", left.lower()))
    tokens_right = set(re.findall(r"\w+", right.lower()))
    if not tokens_left or not tokens_right:
        return 0.0
    left_sorted = " ".join(sorted(tokens_left))
    right_sorted = " ".join(sorted(tokens_right))
    return SequenceMatcher(None, left_sorted, right_sorted).ratio()


def compute_confidence(tender_title: str, article_title: str, region: str | None = None) -> float:
    """Вычислить уровень уверенности сопоставления.

    :param tender_title: Название тендера.
    :param article_title: Заголовок статьи.
    :param region: Регион, если известен.
    :return: Значение confidence_score от 0 до 1.
    """

    title_score = _token_set_ratio(tender_title, article_title)
    region_score = 0.1 if region and region.lower() in article_title.lower() else 0.0
    raw_score = min(title_score + region_score, 1.0)
    return raw_score


def diff_fields(left: dict, right: dict, fields: list[str]) -> dict[str, dict[str, str]]:
    """Сравнить набор полей двух источников.

    :param left: Поля из первого источника.
    :param right: Поля из второго источника.
    :param fields: Список ключей для сравнения.
    :return: Словарь расхождений по полям.
    """

    diff: dict[str, dict[str, str]] = {}
    for field in fields:
        left_value = str(left.get(field, ""))
        right_value = str(right.get(field, ""))
        if left_value != right_value:
            diff[field] = {"left": left_value, "right": right_value}
    return diff
