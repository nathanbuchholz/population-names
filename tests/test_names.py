import pytest


@pytest.mark.asyncio
async def test_create_user_entry(client):
    resp = await client.post(
        "/api/v1/names",
        json={
            "name": "TestName",
            "name_type": "forename",
            "gender_code": "F",
            "year": 2020,
            "count": 100,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "TestName"
    assert data["id"] is not None
    entry_id = data["id"]

    # Update
    resp = await client.put(
        f"/api/v1/names/{entry_id}",
        json={
            "name": "TestNameUpdated",
            "name_type": "forename",
            "gender_code": "F",
            "year": 2020,
            "count": 200,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "TestNameUpdated"

    # Delete
    resp = await client.delete(f"/api/v1/names/{entry_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_forename_not_found(client):
    resp = await client.get("/api/v1/forenames/NonexistentName12345")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_surname_not_found(client):
    resp = await client.get("/api/v1/surnames/NonexistentName12345")
    assert resp.status_code == 404
