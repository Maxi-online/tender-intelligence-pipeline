"""Дедупликация проектов.

Автор: Maxi-online
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_title_cache import ProjectTitleCache
from app.services.llm_processing import (
    classify_project_titles,
    normalize_project_titles,
    choose_best_project,
    find_duplicate_project_groups,
)


def normalize_project_name(name: str) -> str:
    """Нормализовать название проекта для сравнения.

    :param name: Исходное название проекта.
    :return: Нормализованная строка.
    """

    lowered = name.lower()
    cleaned = re.sub(r"[\"'«»]", "", lowered)
    cleaned = re.sub(r"[^a-zа-я0-9]+", " ", cleaned)
    tokens = [token for token in cleaned.split() if token]
    return " ".join(tokens).strip()


async def dedupe_projects(session: AsyncSession) -> dict[str, int]:
    """Склеить дубликаты проектов по нормализованному названию.

    :param session: Асинхронная сессия БД.
    :return: Статистика склейки.
    """

    projects = (await session.execute(select(Project))).scalars().all()
    names = [p.name for p in projects if p.name]
    noise_titles: set[str] = set()
    if names:
        batch_size = 20
        for idx in range(0, len(names), batch_size):
            batch = names[idx : idx + batch_size]
            try:
                mapping = await classify_project_titles(batch)
            except Exception:  # noqa: BLE001
                mapping = {}
            for title in batch:
                if mapping.get(title) is True:
                    noise_titles.add(title)
    cached_rows = await session.execute(
        select(ProjectTitleCache).where(ProjectTitleCache.original_title.in_(names))
    )
    cached = {row.original_title: row.canonical_title for row in cached_rows.scalars().all()}
    missing = [name for name in names if name not in cached]
    if missing:
        batch_size = 20
        for idx in range(0, len(missing), batch_size):
            batch = missing[idx : idx + batch_size]
            try:
                mapping = await normalize_project_titles(batch)
            except Exception:  # noqa: BLE001
                mapping = {}
            for original in batch:
                canonical = mapping.get(original, "").strip() or original
                cached[original] = canonical
                session.add(
                    ProjectTitleCache(
                        original_title=original,
                        canonical_title=canonical,
                    )
                )
        await session.commit()

    merged = 0
    normalized: list[tuple[str, Project]] = []
    for project in projects:
        if project.name and project.name in noise_titles:
            await session.delete(project)
            merged += 1
            continue
        canonical_name = cached.get(project.name, project.name)
        normalized.append((normalize_project_name(canonical_name), project))
    kept: dict[str, Project] = {}
    for key, project in normalized:
        if key not in kept:
            kept[key] = project
            continue
        # Дубликат: выбор победителя через OpenAI
        candidates = [kept[key], project]
        payload = [
            {
                "id": p.id,
                "name": p.name,
                "region": p.region,
                "stage": p.stage,
                "budget": p.budget,
                "customer": p.customer_name,
                "contractor": p.contractor_name,
                "investor": p.investor_name,
                "customer_email": p.customer_email,
                "customer_phone": p.customer_phone,
                "description": p.description,
                "sources": p.source_urls,
            }
            for p in candidates
        ]
        keep_id = await choose_best_project(payload)
        if keep_id == kept[key].id:
            await session.delete(project)
        else:
            await session.delete(kept[key])
            kept[key] = project
        merged += 1

    await session.commit()

    # Второй проход: дубликаты по доказательствам (один регион, цена, заказчик, исполнитель)
    projects_left = (await session.execute(select(Project))).scalars().all()
    evidence_batch_size = 25
    for idx in range(0, len(projects_left), evidence_batch_size):
        batch = projects_left[idx : idx + evidence_batch_size]
        payloads = [
            {
                "id": p.id,
                "name": p.name,
                "region": p.region,
                "stage": p.stage,
                "budget": p.budget,
                "customer": p.customer_name,
                "contractor": p.contractor_name,
                "investor": p.investor_name,
                "customer_email": p.customer_email,
                "customer_phone": p.customer_phone,
                "description": (p.description or "")[:500],
                "sources": p.source_urls,
            }
            for p in batch
        ]
        try:
            groups = await find_duplicate_project_groups(payloads)
        except Exception:  # noqa: BLE001
            groups = []
        for group_ids in groups:
            group_projects = [p for p in batch if p.id in group_ids]
            if len(group_projects) < 2:
                continue
            candidates = [
                {
                    "id": p.id,
                    "name": p.name,
                    "region": p.region,
                    "stage": p.stage,
                    "budget": p.budget,
                    "customer": p.customer_name,
                    "contractor": p.contractor_name,
                    "investor": p.investor_name,
                    "customer_email": p.customer_email,
                    "customer_phone": p.customer_phone,
                    "description": p.description,
                    "sources": p.source_urls,
                }
                for p in group_projects
            ]
            keep_id = await choose_best_project(candidates)
            if keep_id is None:
                continue
            kept = next((p for p in group_projects if p.id == keep_id), None)
            if not kept:
                continue
            for p in group_projects:
                if p.id == keep_id:
                    continue
                if p.source_urls:
                    merged_urls = (kept.source_urls or []) + (p.source_urls or [])
                    kept.source_urls = list(dict.fromkeys(merged_urls))
                await session.delete(p)
                merged += 1

    await session.commit()
    return {"merged": merged}
