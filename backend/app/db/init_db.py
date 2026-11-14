"""Initialization of the database structure.

Author: Maxi-online
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.db.session import engine
from app.models.base import Base


async def create_all() -> None:
    """Create all tables in the database.

    :return: None. The function creates tables if they are not available.
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE companies "
                "ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS description TEXT"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS customer_name VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS customer_email VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(64)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS investor_name VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS investor_email VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS investor_phone VARCHAR(64)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS contractor_name VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS contractor_email VARCHAR(256)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS contractor_phone VARCHAR(64)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE projects "
                "ADD COLUMN IF NOT EXISTS source_urls JSON"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_companies_normalized_name "
                "ON companies (normalized_name)"
            )
        )
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_normalized_name "
                "ON projects (normalized_name)"
            )
        )


def init_db() -> None:
    """Start creating tables in a synchronous context.

    :return: None. The function causes the creation of tables.
    """

    asyncio.run(create_all())


if __name__ == "__main__":
    init_db()
