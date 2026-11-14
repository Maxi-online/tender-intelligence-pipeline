"""Normalization of values: telephones, dates, currencies.

Author: Maxi-online
"""

from __future__ import annotations

import re

from dateutil import parser


PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone(raw_phone: str) -> str:
    """Normalize the telephone to +7XXXXXXX.

    :param raw_phone: Telephone in arbitrary format.
    :return: Normalized telephone.
    """

    digits = PHONE_DIGITS.sub("", raw_phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not digits.startswith("7"):
        digits = "7" + digits[-10:]
    return f"+{digits}"


def normalize_date(raw_date: str) -> str:
    """Normalize the date in ISO 8601.

    :param raw_date: Date in arbitrary format.
    :return: Date in ISO 8601 format.
    """

    parsed = parser.parse(raw_date, dayfirst=True)
    return parsed.date().isoformat()


def normalize_currency(raw_currency: str) -> str:
    """Normalize the currency to ISO 4217.

    :param raw_currency: Currency in arbitrary form.
    :return: ISO 4217 currency code.
    """

    lowered = raw_currency.lower()
    if "руб" in lowered or "₽" in raw_currency:
        return "RUB"
    if "usd" in lowered or "$" in raw_currency:
        return "USD"
    if "eur" in lowered or "€" in raw_currency:
        return "EUR"
    return raw_currency.upper()
