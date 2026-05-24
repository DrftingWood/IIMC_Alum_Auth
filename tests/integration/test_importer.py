from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.import_directory import import_directory
from src.shared.models import Alumni
from tests.fixtures.make_sample_xlsx import write as write_sample


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    p = tmp_path / "sample.xlsx"
    write_sample(p)
    return p


@pytest.mark.asyncio
async def test_import_inserts_all_rows(session: AsyncSession, sample_xlsx: Path) -> None:
    summary = await import_directory(session, sample_xlsx)
    await session.flush()
    assert summary.inserted == 51
    assert summary.updated == 0

    count = (await session.execute(select(func.count()).select_from(Alumni))).scalar_one()
    assert count == 51


@pytest.mark.asyncio
async def test_import_is_idempotent(session: AsyncSession, sample_xlsx: Path) -> None:
    await import_directory(session, sample_xlsx)
    await session.flush()
    summary2 = await import_directory(session, sample_xlsx)
    await session.flush()
    assert summary2.inserted == 0
    assert summary2.updated == 51


@pytest.mark.asyncio
async def test_import_preserves_extra_columns(session: AsyncSession, sample_xlsx: Path) -> None:
    await import_directory(session, sample_xlsx)
    await session.flush()
    a = await session.get(Alumni, "sample001")
    assert a is not None
    assert a.extra.get("Hostel") == "OH"
    assert "UG Degree" in a.extra
