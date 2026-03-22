import pytest


@pytest.mark.asyncio
async def test_missing_api_key_rejected(raw_client):
    resp = await raw_client.get("/api/v1/forenames")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_invalid_api_key_returns_403(raw_client):
    resp = await raw_client.get(
        "/api/v1/forenames",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_does_not_require_api_key(raw_client):
    resp = await raw_client.get("/health")
    assert resp.status_code == 200
