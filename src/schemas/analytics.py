"""Pydantic schemas for ranked name analytics and comparison responses."""

from pydantic import BaseModel, field_validator

from src.schemas.common import PaginatedResponse, coerce_date_to_year


class RankedForenameItem(BaseModel):
    name: str
    gender_code: str
    country_name: str
    year: int
    count: int
    rank: int
    pct_of_year_total: float | None

    model_config = {"from_attributes": True}

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class RankedForenameResponse(PaginatedResponse):
    items: list[RankedForenameItem]


class RankedSurnameItem(BaseModel):
    name: str
    country_name: str
    year: int
    count: int
    rank: int
    pct_of_year_total: float | None

    model_config = {"from_attributes": True}

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class RankedSurnameResponse(PaginatedResponse):
    items: list[RankedSurnameItem]


class ComparePoint(BaseModel):
    year: int
    count: int

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class CompareNameData(BaseModel):
    name: str
    data: list[ComparePoint]


class CompareResponse(BaseModel):
    country: str
    names: list[CompareNameData]
