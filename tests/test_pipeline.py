"""Tests for the pipeline trigger and status endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_pipeline_status(client, db_session):
    with patch("src.api.routers.pipeline._airflow_headers", new_callable=AsyncMock):
        resp = await client.get("/api/v1/pipeline/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "row_counts" in data


@pytest.mark.asyncio
async def test_pipeline_trigger_calls_airflow(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"dag_run_id": "test-run-123"}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client

    with (
        patch(
            "src.api.routers.pipeline._airflow_headers",
            new_callable=AsyncMock,
            return_value={"Authorization": "Bearer fake"},
        ),
        patch(
            "src.api.routers.pipeline.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        resp = await client.post("/api/v1/pipeline/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["dag_run_id"] == "test-run-123"
