"""Нормализация значений: телефоны, даты, валюты.

Автор: Maxi-online
"""

from __future__ import annotations

import re

from dateutil import parser


PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone(raw_phone: str) -> str:
    """Нормализовать телефон к формату +7XXXXXXXXXX.

    :param raw_phone: Телефон в произвольном формате.
    :return: Нормализованный телефон.
    """

    digits = PHONE_DIGITS.sub("", raw_phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not digits.startswith("7"):
        digits = "7" + digits[-10:]
    return f"+{digits}"


def normalize_date(raw_date: str) -> str:
    """Нормализовать дату в ISO 8601.

    :param raw_date: Дата в произвольном формате.
    :return: Дата в формате ISO 8601.
    """

    parsed = parser.parse(raw_date, dayfirst=True)
    return parsed.date().isoformat()


def normalize_currency(raw_currency: str) -> str:
    """Нормализовать валюту к ISO 4217.

    :param raw_currency: Валюта в произвольной форме.
    :return: Код валюты ISO 4217.
    """

    lowered = raw_currency.lower()
    if "руб" in lowered or "₽" in raw_currency:
        return "RUB"
    if "usd" in lowered or "$" in raw_currency:
        return "USD"
    if "eur" in lowered or "€" in raw_currency:
        return "EUR"
    return raw_currency.upper()
