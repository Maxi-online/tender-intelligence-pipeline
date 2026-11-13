"""Дедупликация и склейка компаний.

Автор: Maxi-online
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company


LEGAL_FORMS = [
    "ооо",
    "оао",
    "пао",
    "зао",
    "ао",
    "ип",
    "нко",
    "гку",
    "мку",
]


def normalize_name(name: str) -> str:
    """Нормализовать название компании для сравнения.

    :param name: Исходное название.
    :return: Нормализованная строка.
    """

    lowered = name.lower()
    for form in LEGAL_FORMS:
        lowered = lowered.replace(form, "")
    lowered = re.sub(r"[\"'«»()]", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _name_similarity(left: str, right: str) -> float:
    """Оценить сходство двух нормализованных названий."""

    return SequenceMatcher(None, left, right).ratio()


async def dedupe_companies(session: AsyncSession) -> dict[str, int]:
    """Склеить дубликаты компаний по ИНН и названию.

    :param session: Асинхронная сессия БД.
    :return: Статистика склейки.
    """

    companies = (await session.execute(select(Company))).scalars().all()
    merged = 0
    for company in companies:
        if company.canonical_id:
            continue
        if company.inn:
            duplicates = [
                c for c in companies if c.id != company.id and c.inn == company.inn
            ]
        else:
            base_name = normalize_name(company.name)
            duplicates = [
                c
                for c in companies
                if c.id != company.id
                and (
                    normalize_name(c.name) == base_name
                    or _name_similarity(normalize_name(c.name), base_name) > 0.92
                )
            ]
        for dup in duplicates:
            dup.canonical_id = company.id
            if not company.phone and dup.phone:
                company.phone = dup.phone
            if not company.email and dup.email:
                company.email = dup.email
            if not company.address and dup.address:
                company.address = dup.address
            merged += 1
    await session.commit()
    return {"merged": merged}
