"""Shared Pydantic schemas: pagination, country/gender responses."""

from datetime import date

from pydantic import BaseModel, Field


def coerce_date_to_year(v):
    if isinstance(v, date):
        return v.year
    return v


class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel):
    total: int
    offset: int
    limit: int


class CountryOut(BaseModel):
    country_id: int
    name: str
    iso_alpha2: str
    iso_alpha3: str
    subdivision_code: str | None

    model_config = {"from_attributes": True}


class GenderOut(BaseModel):
    gender_id: int
    code: str
    label: str

    model_config = {"from_attributes": True}
