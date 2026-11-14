"""Comparison of entities between sources.

Author: Maxi-online
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def _token_set_ratio(left: str, right: str) -> float:
    'token_set_ratio parallel without external dependence.'

    tokens_left = set(re.findall(r"\w+", left.lower()))
    tokens_right = set(re.findall(r"\w+", right.lower()))
    if not tokens_left or not tokens_right:
        return 0.0
    left_sorted = " ".join(sorted(tokens_left))
    right_sorted = " ".join(sorted(tokens_right))
    return SequenceMatcher(None, left_sorted, right_sorted).ratio()


def compute_confidence(tender_title: str, article_title: str, region: str | None = None) -> float:
    """Calculate the level of confidence of the comparison.

    :param tender_title: Name of tender.
    :param article_title: Title of the article.
    :param region: Region, if known.
    :return: value of confidence_score between 0 and 1.
    """

    title_score = _token_set_ratio(tender_title, article_title)
    region_score = 0.1 if region and region.lower() in article_title.lower() else 0.0
    raw_score = min(title_score + region_score, 1.0)
    return raw_score


def diff_fields(left: dict, right: dict, fields: list[str]) -> dict[str, dict[str, str]]:
    """Compare the set of fields of the two sources.

    :param left: Fields from the first source.
    :param right: Fields from second source.
    :param fields: A list of keys for comparison.
    :return: Vocabulary of Field Discrepancies.
    """

    diff: dict[str, dict[str, str]] = {}
    for field in fields:
        left_value = str(left.get(field, ""))
        right_value = str(right.get(field, ""))
        if left_value != right_value:
            diff[field] = {"left": left_value, "right": right_value}
    return diff
