from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"


@pytest.mark.asyncio
async def test_health_db_down(client):
    with patch(
        "src.api.routers.health.SessionDep",
    ):
        mock_session = AsyncMock()
        mock_session.execute.side_effect = ConnectionError("db down")

        from src.api.routers.health import health

        result = await health(session=mock_session)
        assert result["database"] == "unhealthy"
