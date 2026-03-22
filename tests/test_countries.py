"""Tests for the countries reference data endpoint."""

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_list_countries(client, db_session):
    await db_session.execute(
        text(
            "INSERT INTO countries (name, iso_alpha2, iso_alpha3, subdivision_code) "
            "VALUES ('United States', 'US', 'USA', NULL) "
            "ON CONFLICT DO NOTHING"
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/countries")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["name"] == "United States"
