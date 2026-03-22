import pytest

# --- Empty-database tests (existing) ---


@pytest.mark.asyncio
async def test_top_forenames_empty(client):
    resp = await client.get("/api/v1/analytics/top-forenames")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_top_surnames_empty(client):
    resp = await client.get("/api/v1/analytics/top-surnames")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_compare_empty(client):
    resp = await client.get(
        "/api/v1/analytics/compare",
        params={
            "names": "Emma,Olivia",
            "country": "US",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["names"]) == 2


# --- Seeded-database tests ---


@pytest.mark.asyncio
async def test_top_forenames(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-forenames")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["items"][0]["name"] == "Emma"
    assert data["items"][0]["rank"] == 1


@pytest.mark.asyncio
async def test_top_forenames_filter_year(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-forenames", params={"year": 2020})
    assert resp.status_code == 200
    assert resp.json()["total"] == 5


@pytest.mark.asyncio
async def test_top_forenames_filter_country(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-forenames", params={"country": "GB-ENG"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["country_name"] == "England and Wales" for item in data["items"])


@pytest.mark.asyncio
async def test_top_forenames_filter_gender(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-forenames", params={"gender": "M"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["gender_code"] == "M" for item in data["items"])


@pytest.mark.asyncio
async def test_top_surnames(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-surnames")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["items"][0]["name"] == "Smith"


@pytest.mark.asyncio
async def test_top_surnames_filter_country(seeded_client):
    resp = await seeded_client.get("/api/v1/analytics/top-surnames", params={"country": "GB-ENG"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Jones"


@pytest.mark.asyncio
async def test_compare(seeded_client):
    resp = await seeded_client.get(
        "/api/v1/analytics/compare",
        params={"names": "James,Mary", "country": "US"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["country"] == "United States"
    assert len(data["names"]) == 2
    james = next(n for n in data["names"] if n["name"] == "James")
    assert len(james["data"]) == 2  # 2020 and 2021


@pytest.mark.asyncio
async def test_pagination(seeded_client):
    resp = await seeded_client.get(
        "/api/v1/analytics/top-forenames",
        params={"offset": 0, "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["offset"] == 0
    assert data["limit"] == 2

    # Second page
    resp = await seeded_client.get(
        "/api/v1/analytics/top-forenames",
        params={"offset": 2, "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["offset"] == 2
