"""Forename and surname list/detail endpoints, plus user entry CRUD."""

from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import delete, func, select, update

from src.api.dependencies import APIKeyDep, SessionDep
from src.db.models import Country, Forename, Gender, Surname, UserNameEntry
from src.schemas.names import (
    ForenameDetailResponse,
    ForenameItem,
    ForenameListResponse,
    NameTimeSeriesPoint,
    SurnameDetailResponse,
    SurnameItem,
    SurnameListResponse,
    UserEntryIn,
    UserEntryOut,
)

router = APIRouter(prefix="/api/v1", tags=["names"])


@router.get("/forenames", response_model=ForenameListResponse)
async def list_forenames(
    session: SessionDep,
    _: APIKeyDep,
    country: str | None = Query(
        None,
        description="ISO alpha-2 or subdivision code (e.g. US, GB-ENG)",
    ),
    gender: str | None = Query(None, pattern=r"^[MF]$"),
    search: str | None = None,
    year: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("name", pattern=r"^(name|count)$"),
    order: str = Query("asc", pattern=r"^(asc|desc)$"),
):
    base = (
        select(
            Forename.name,
            Gender.code.label("gender_code"),
            Country.name.label("country_name"),
            Forename.year,
            Forename.count,
        )
        .join(Gender, Forename.gender_id == Gender.gender_id)
        .join(Country, Forename.country_id == Country.country_id)
    )

    if search:
        base = base.where(Forename.name.ilike(f"%{search}%"))
    if gender:
        base = base.where(Gender.code == gender)
    if country:
        base = base.where((Country.iso_alpha2 == country) | (Country.subdivision_code == country))
    if year:
        base = base.where(Forename.year == date_type(year, 1, 1))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar_one()

    sort_col = Forename.name if sort_by == "name" else Forename.count
    if order == "desc":
        sort_col = sort_col.desc()
    base = base.order_by(sort_col).offset(offset).limit(limit)

    rows = (await session.execute(base)).all()
    items = [
        ForenameItem(
            name=r.name,
            gender_code=r.gender_code,
            country_name=r.country_name,
            year=r.year,
            count=r.count,
        )
        for r in rows
    ]
    return ForenameListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/forenames/{name}", response_model=ForenameDetailResponse)
async def get_forename(
    session: SessionDep,
    _: APIKeyDep,
    name: str,
    gender: str | None = Query(None, pattern=r"^[MF]$"),
):
    q = (
        select(
            Forename.year,
            Country.name.label("country_name"),
            Gender.code.label("gender_code"),
            Forename.count,
        )
        .join(Gender, Forename.gender_id == Gender.gender_id)
        .join(Country, Forename.country_id == Country.country_id)
        .where(Forename.name.ilike(name))
        .order_by(Country.name, Forename.year)
    )
    if gender:
        q = q.where(Gender.code == gender)

    rows = (await session.execute(q)).all()
    if not rows:
        raise HTTPException(404, "Forename not found")

    gender_code = rows[0].gender_code
    series: dict[str, list[NameTimeSeriesPoint]] = {}
    for r in rows:
        series.setdefault(r.country_name, []).append(
            NameTimeSeriesPoint(year=r.year, count=r.count)
        )
    return ForenameDetailResponse(name=name, gender_code=gender_code, series=series)


@router.get("/surnames", response_model=SurnameListResponse)
async def list_surnames(
    session: SessionDep,
    _: APIKeyDep,
    country: str | None = Query(
        None,
        description="ISO alpha-2 or subdivision code (e.g. US, GB-ENG)",
    ),
    search: str | None = None,
    year: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("name", pattern=r"^(name|count)$"),
    order: str = Query("asc", pattern=r"^(asc|desc)$"),
):
    base = select(
        Surname.name,
        Country.name.label("country_name"),
        Surname.year,
        Surname.count,
    ).join(Country, Surname.country_id == Country.country_id)

    if search:
        base = base.where(Surname.name.ilike(f"%{search}%"))
    if country:
        base = base.where((Country.iso_alpha2 == country) | (Country.subdivision_code == country))
    if year:
        base = base.where(Surname.year == date_type(year, 1, 1))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar_one()

    sort_col = Surname.name if sort_by == "name" else Surname.count
    if order == "desc":
        sort_col = sort_col.desc()
    base = base.order_by(sort_col).offset(offset).limit(limit)

    rows = (await session.execute(base)).all()
    items = [
        SurnameItem(
            name=r.name,
            country_name=r.country_name,
            year=r.year,
            count=r.count,
        )
        for r in rows
    ]
    return SurnameListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/surnames/{name}", response_model=SurnameDetailResponse)
async def get_surname(session: SessionDep, _: APIKeyDep, name: str):
    q = (
        select(
            Surname.year,
            Country.name.label("country_name"),
            Surname.count,
        )
        .join(Country, Surname.country_id == Country.country_id)
        .where(Surname.name.ilike(name))
        .order_by(Country.name, Surname.year)
    )
    rows = (await session.execute(q)).all()
    if not rows:
        raise HTTPException(404, "Surname not found")

    series: dict[str, list[NameTimeSeriesPoint]] = {}
    for r in rows:
        series.setdefault(r.country_name, []).append(
            NameTimeSeriesPoint(year=r.year, count=r.count)
        )
    return SurnameDetailResponse(name=name, series=series)


# CRUD for user entries
@router.post("/names", response_model=UserEntryOut, status_code=201)
async def create_user_entry(session: SessionDep, _: APIKeyDep, entry: UserEntryIn):
    obj = UserNameEntry(**entry.to_db_dict())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.put("/names/{entry_id}", response_model=UserEntryOut)
async def update_user_entry(session: SessionDep, _: APIKeyDep, entry_id: int, entry: UserEntryIn):
    result = await session.execute(
        update(UserNameEntry)
        .where(UserNameEntry.id == entry_id)
        .values(**entry.to_db_dict())
        .returning(UserNameEntry)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Entry not found")
    await session.commit()
    return obj


@router.delete("/names/{entry_id}", status_code=204)
async def delete_user_entry(session: SessionDep, _: APIKeyDep, entry_id: int):
    result = await session.execute(delete(UserNameEntry).where(UserNameEntry.id == entry_id))
    if result.rowcount == 0:
        raise HTTPException(404, "Entry not found")
    await session.commit()
