"""Shared test fixtures for API and integration tests."""

import datetime
import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.dependencies import verify_api_key
from src.api.main import app
from src.db.models import Base
from src.db.session import get_session

def _get_test_db_url() -> str:
    """Derive test DB URL: use TEST_DATABASE_URL env var, or swap the DB name in settings."""
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    from src.api.config import settings

    base = settings.database_url
    # Replace the database name with the test database
    return base.rsplit("/", 1)[0] + "/population_names_test"


TEST_DATABASE_URL = _get_test_db_url()

engine = create_async_engine(TEST_DATABASE_URL, pool_size=5, max_overflow=0, pool_pre_ping=True)
test_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def override_get_session():
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session
app.dependency_overrides[verify_api_key] = lambda: "test-key"


@pytest_asyncio.fixture
async def db_session():
    # Use a fresh engine per test to avoid asyncpg connection state issues
    local_engine = create_async_engine(
        TEST_DATABASE_URL, pool_size=2, max_overflow=0, pool_pre_ping=True
    )
    local_factory = async_sessionmaker(local_engine, expire_on_commit=False)

    # Temporarily swap the override to use this test's engine
    async def local_get_session():
        async with local_factory() as s:
            yield s

    app.dependency_overrides[get_session] = local_get_session

    async with local_engine.begin() as conn:
        for schema in ("raw", "staging"):
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        await conn.run_sync(Base.metadata.create_all)

    async with local_factory() as session:
        yield session

    async with local_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await local_engine.dispose()
    app.dependency_overrides[get_session] = override_get_session


@pytest_asyncio.fixture
async def client(db_session):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def raw_client(db_session):
    """Client without API key override -- requests must provide their own auth."""
    saved = app.dependency_overrides.pop(verify_api_key, None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    if saved is not None:
        app.dependency_overrides[verify_api_key] = saved


@pytest_asyncio.fixture
async def seeded_client(db_session):
    """Client with reference data seeded into all tables and materialized views."""
    d = datetime.date

    # Dimension tables
    await db_session.execute(
        text("""
        INSERT INTO countries
            (country_id, name, iso_alpha2, iso_alpha3, subdivision_code)
        VALUES
            (1, 'United States', 'US', 'USA', NULL),
            (2, 'England and Wales', 'GB', 'GBR', 'GB-ENG')
    """)
    )
    await db_session.execute(
        text("""
        INSERT INTO genders (gender_id, code, label) VALUES
            (1, 'M', 'Male'), (2, 'F', 'Female')
    """)
    )

    # Forenames
    from src.db.models import Forename

    forenames = [
        Forename(name="James", gender_id=1, country_id=1, year=d(2020, 1, 1), count=5000),
        Forename(name="James", gender_id=1, country_id=1, year=d(2021, 1, 1), count=4800),
        Forename(name="Mary", gender_id=2, country_id=1, year=d(2020, 1, 1), count=4500),
        Forename(name="Mary", gender_id=2, country_id=1, year=d(2021, 1, 1), count=4200),
        Forename(name="Oliver", gender_id=1, country_id=2, year=d(2020, 1, 1), count=3000),
        Forename(name="Olivia", gender_id=2, country_id=2, year=d(2020, 1, 1), count=3500),
        Forename(name="Alex", gender_id=1, country_id=1, year=d(2020, 1, 1), count=1000),
        Forename(name="Alex", gender_id=2, country_id=1, year=d(2020, 1, 1), count=900),
        Forename(name="Emma", gender_id=2, country_id=1, year=d(2020, 1, 1), count=6000),
        Forename(name="Emma", gender_id=2, country_id=2, year=d(2020, 1, 1), count=2000),
    ]
    db_session.add_all(forenames)

    # Surnames
    from src.db.models import Surname

    surnames = [
        Surname(name="Smith", country_id=1, year=d(2020, 1, 1), count=10000),
        Surname(name="Johnson", country_id=1, year=d(2020, 1, 1), count=8000),
        Surname(name="Williams", country_id=1, year=d(2020, 1, 1), count=7000),
        Surname(name="Jones", country_id=2, year=d(2020, 1, 1), count=6000),
        Surname(name="Taylor", country_id=2, year=d(2020, 1, 1), count=5500),
    ]
    db_session.add_all(surnames)

    # MV: forename rankings
    await db_session.execute(
        text("""
        INSERT INTO mv_forename_rankings
            (name, gender_id, country_id, year, count, rank, pct_of_year_total)
        VALUES
            ('Emma', 2, 1, '2020-01-01', 6000, 1, 5.2),
            ('James', 1, 1, '2020-01-01', 5000, 2, 4.3),
            ('Mary', 2, 1, '2020-01-01', 4500, 3, 3.9),
            ('Olivia', 2, 2, '2020-01-01', 3500, 1, 6.1),
            ('Oliver', 1, 2, '2020-01-01', 3000, 2, 5.5)
    """)
    )

    # MV: surname rankings
    await db_session.execute(
        text("""
        INSERT INTO mv_surname_rankings
            (name, country_id, year, count, rank, pct_of_year_total)
        VALUES
            ('Smith', 1, '2020-01-01', 10000, 1, 8.5),
            ('Johnson', 1, '2020-01-01', 8000, 2, 6.8),
            ('Jones', 2, '2020-01-01', 6000, 1, 7.2)
    """)
    )

    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
