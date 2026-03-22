"""Analytics endpoints: top names, rankings, and cross-name comparisons."""

from datetime import date as date_type

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.api.dependencies import APIKeyDep, SessionDep
from src.db.models import (
    Country,
    Forename,
    Gender,
    MvForenameRanking,
    MvSurnameRanking,
)
from src.schemas.analytics import (
    CompareNameData,
    ComparePoint,
    CompareResponse,
    RankedForenameItem,
    RankedForenameResponse,
    RankedSurnameItem,
    RankedSurnameResponse,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/top-forenames", response_model=RankedForenameResponse)
async def top_forenames(
    session: SessionDep,
    _: APIKeyDep,
    year: int | None = None,
    country: str | None = Query(
        None,
        description="ISO alpha-2 or subdivision code (e.g. US, GB-ENG)",
    ),
    gender: str | None = Query(None, pattern=r"^[MF]$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    q = (
        select(
            MvForenameRanking.name,
            Gender.code.label("gender_code"),
            Country.name.label("country_name"),
            MvForenameRanking.year,
            MvForenameRanking.count,
            MvForenameRanking.rank,
            MvForenameRanking.pct_of_year_total,
        )
        .join(Gender, MvForenameRanking.gender_id == Gender.gender_id)
        .join(Country, MvForenameRanking.country_id == Country.country_id)
    )
    if year:
        q = q.where(MvForenameRanking.year == date_type(year, 1, 1))
    if country:
        q = q.where((Country.iso_alpha2 == country) | (Country.subdivision_code == country))
    if gender:
        q = q.where(Gender.code == gender)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await session.execute(count_q)).scalar_one()

    q = q.order_by(MvForenameRanking.rank).offset(offset).limit(limit)
    rows = (await session.execute(q)).all()
    items = [
        RankedForenameItem(
            name=r.name,
            gender_code=r.gender_code,
            country_name=r.country_name,
            year=r.year,
            count=r.count,
            rank=r.rank,
            pct_of_year_total=float(r.pct_of_year_total) if r.pct_of_year_total else None,
        )
        for r in rows
    ]
    return RankedForenameResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/top-surnames", response_model=RankedSurnameResponse)
async def top_surnames(
    session: SessionDep,
    _: APIKeyDep,
    year: int | None = None,
    country: str | None = Query(
        None,
        description="ISO alpha-2 or subdivision code (e.g. US, GB-ENG)",
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    q = select(
        MvSurnameRanking.name,
        Country.name.label("country_name"),
        MvSurnameRanking.year,
        MvSurnameRanking.count,
        MvSurnameRanking.rank,
        MvSurnameRanking.pct_of_year_total,
    ).join(Country, MvSurnameRanking.country_id == Country.country_id)
    if year:
        q = q.where(MvSurnameRanking.year == date_type(year, 1, 1))
    if country:
        q = q.where((Country.iso_alpha2 == country) | (Country.subdivision_code == country))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await session.execute(count_q)).scalar_one()

    q = q.order_by(MvSurnameRanking.rank).offset(offset).limit(limit)
    rows = (await session.execute(q)).all()
    items = [
        RankedSurnameItem(
            name=r.name,
            country_name=r.country_name,
            year=r.year,
            count=r.count,
            rank=r.rank,
            pct_of_year_total=float(r.pct_of_year_total) if r.pct_of_year_total else None,
        )
        for r in rows
    ]
    return RankedSurnameResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/compare", response_model=CompareResponse)
async def compare(
    session: SessionDep,
    _: APIKeyDep,
    names: str = Query(..., description="Comma-separated names"),
    country: str = Query(
        "US",
        description="ISO alpha-2 or subdivision code (e.g. US, GB-ENG)",
    ),
):
    name_list = [n.strip() for n in names.split(",")]

    country_row = (
        await session.execute(
            select(Country).where(
                (Country.iso_alpha2 == country) | (Country.subdivision_code == country)
            )
        )
    ).scalar_one_or_none()
    country_name = country_row.name if country_row else country

    result_names: list[CompareNameData] = []
    for name in name_list:
        q = (
            select(Forename.year, Forename.count)
            .join(Country, Forename.country_id == Country.country_id)
            .where(Forename.name.ilike(name))
            .where((Country.iso_alpha2 == country) | (Country.subdivision_code == country))
            .order_by(Forename.year)
        )
        rows = (await session.execute(q)).all()
        result_names.append(
            CompareNameData(
                name=name,
                data=[ComparePoint(year=r.year, count=r.count) for r in rows],
            )
        )
    return CompareResponse(country=country_name, names=result_names)
