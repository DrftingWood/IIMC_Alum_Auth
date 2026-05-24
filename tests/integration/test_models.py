import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_database_is_up(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1 AS ok"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_alumni_table_exists(session: AsyncSession) -> None:
    result = await session.execute(
        text("SELECT count(*) FROM information_schema.tables " "WHERE table_name = 'alumni'")
    )
    assert result.scalar_one() == 1
