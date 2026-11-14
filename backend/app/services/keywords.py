"""Tools to work with key words sets.

Author: Adaptation to TPIS.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.keyword import SearchKeyword, SearchKeywordSet
from app.services.config_loader import load_keywords_config


async def list_keyword_sets(session: AsyncSession) -> list[SearchKeywordSet]:
    'Get all keyword sets with keys preset.'

    result = await session.execute(
        select(SearchKeywordSet).options(selectinload(SearchKeywordSet.keywords))
    )
    sets: list[SearchKeywordSet] = list(result.scalars().all())
    return sets


async def get_keyword_set(session: AsyncSession, set_id: int) -> SearchKeywordSet | None:
    'Get one set by identifier.'

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
    'Create a set of key words.'

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
    """Update the parameters of the set of key words.

    If the kywords list is transferred, the existing selection keys will be rewritten.
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
    'Delete the set of key words.'

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
    """Get a list of the text keys for the set.

    If set_id = = None or set not found, the empty list returns.
    """

    if set_id is None:
        return []
    keyword_set = await get_keyword_set(session, set_id)
    if not keyword_set:
        return []
    return [item.text for item in keyword_set.keywords if item.text]


async def bootstrap_keyword_sets_from_yaml(session: AsyncSession) -> None:
    'Create a core set of key words from config/keywords.yaml if the database is empty.'

    existing = await session.execute(select(SearchKeywordSet))
    if existing.scalars().first():
        return

    cfg = load_keywords_config()
    construction_keywords: list[str] = cfg.get("construction_keywords", []) or []
    if not construction_keywords:
        return

    await create_keyword_set(
        session,
        name='Construction tenders',
        description='Core set of key words from config/keywords.yaml',
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

