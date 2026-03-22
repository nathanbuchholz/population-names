"""Tests for the genders reference data endpoint."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_list_genders(client, db_session):
    await db_session.execute(
        text(
            "INSERT INTO genders (code, label) VALUES ('M', 'Male') ON CONFLICT (code) DO NOTHING"
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/genders")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
