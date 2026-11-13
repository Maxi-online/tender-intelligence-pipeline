"""Сервисы для работы с наборами ключевых слов.

Автор: адаптация под TPIS.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.keyword import SearchKeyword, SearchKeywordSet
from app.services.config_loader import load_keywords_config


async def list_keyword_sets(session: AsyncSession) -> list[SearchKeywordSet]:
    """Получить все наборы ключевых слов с предзагрузкой ключей."""

    result = await session.execute(
        select(SearchKeywordSet).options(selectinload(SearchKeywordSet.keywords))
    )
    sets: list[SearchKeywordSet] = list(result.scalars().all())
    return sets


async def get_keyword_set(session: AsyncSession, set_id: int) -> SearchKeywordSet | None:
    """Получить один набор по идентификатору."""

    result = await session.execute(
        select(SearchKeywordSet)
        .where(SearchKeywordSet.id == set_id)
        .options(selectinload(SearchKeywordSet.keywords))
    )
    item = result.scalars().first()
    return item


async def create_keyword_set(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    created_by: str | None,
    keywords: Iterable[tuple[str, float]] | None = None,
) -> SearchKeywordSet:
    """Создать набор ключевых слов."""

    keyword_set = SearchKeywordSet(
        name=name,
        description=description,
        created_by=created_by,
    )
    if keywords:
        for text, weight in keywords:
            keyword_set.keywords.append(
                SearchKeyword(
                    text=text,
                    weight=weight,
                )
            )
    session.add(keyword_set)
    await session.commit()
    await session.refresh(keyword_set)
    _ = list(keyword_set.keywords)
    return keyword_set


async def update_keyword_set(
    session: AsyncSession,
    set_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    created_by: str | None = None,
    keywords: Iterable[tuple[str, float]] | None = None,
) -> SearchKeywordSet | None:
    """Обновить параметры набора ключевых слов.

    Если передан список keywords, существующие ключи набора будут перезаписаны.
    """

    keyword_set = await get_keyword_set(session, set_id)
    if not keyword_set:
        return None
    if name is not None:
        keyword_set.name = name
    if description is not None:
        keyword_set.description = description
    if created_by is not None:
        keyword_set.created_by = created_by
    if keywords is not None:
        keyword_set.keywords.clear()
        for text, weight in keywords:
            keyword_set.keywords.append(SearchKeyword(text=text, weight=weight))
    await session.commit()
    await session.refresh(keyword_set)
    _ = list(keyword_set.keywords)
    return keyword_set


async def delete_keyword_set(session: AsyncSession, set_id: int) -> bool:
    """Удалить набор ключевых слов."""

    keyword_set = await get_keyword_set(session, set_id)
    if not keyword_set:
        return False
    await session.delete(keyword_set)
    await session.commit()
    return True


async def resolve_keywords_for_set(
    session: AsyncSession,
    set_id: int | None,
) -> list[str]:
    """Получить список текстовых ключей для указанного набора.

    Если set_id == None или набор не найден, возвращается пустой список.
    """

    if set_id is None:
        return []
    keyword_set = await get_keyword_set(session, set_id)
    if not keyword_set:
        return []
    return [item.text for item in keyword_set.keywords if item.text]


async def bootstrap_keyword_sets_from_yaml(session: AsyncSession) -> None:
    """Создать базовый набор ключевых слов из config/keywords.yaml, если в БД пусто."""

    existing = await session.execute(select(SearchKeywordSet))
    if existing.scalars().first():
        return

    cfg = load_keywords_config()
    construction_keywords: list[str] = cfg.get("construction_keywords", []) or []
    if not construction_keywords:
        return

    await create_keyword_set(
        session,
        name="Строительные тендеры",
        description="Базовый набор ключевых слов из config/keywords.yaml",
        created_by="system",
        keywords=[(kw, 1.0) for kw in construction_keywords],
    )


__all__ = [
    "list_keyword_sets",
    "get_keyword_set",
    "create_keyword_set",
    "update_keyword_set",
    "delete_keyword_set",
    "resolve_keywords_for_set",
    "bootstrap_keyword_sets_from_yaml",
]

