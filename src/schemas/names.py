"""Pydantic schemas for forename/surname queries, detail views, and user entries."""

from datetime import date

from pydantic import BaseModel, Field, field_validator

from src.schemas.common import PaginatedResponse, coerce_date_to_year


class ForenameItem(BaseModel):
    name: str
    gender_code: str
    country_name: str
    year: int
    count: int

    model_config = {"from_attributes": True}

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class ForenameListResponse(PaginatedResponse):
    items: list[ForenameItem]


class SurnameItem(BaseModel):
    name: str
    country_name: str
    year: int
    count: int

    model_config = {"from_attributes": True}

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class SurnameListResponse(PaginatedResponse):
    items: list[SurnameItem]


class NameTimeSeriesPoint(BaseModel):
    year: int
    count: int

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)


class ForenameDetailResponse(BaseModel):
    name: str
    gender_code: str
    series: dict[str, list[NameTimeSeriesPoint]]  # keyed by country_name


class SurnameDetailResponse(BaseModel):
    name: str
    series: dict[str, list[NameTimeSeriesPoint]]  # keyed by country_name


class UserEntryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    name_type: str = Field("forename", pattern=r"^(forename|surname)$")
    country_code: str | None = None
    gender_code: str | None = Field(None, pattern=r"^[MF]$")
    year: int | None = Field(None, ge=1800, le=2100)
    count: int | None = Field(None, ge=0)
    notes: str | None = None

    def to_db_dict(self) -> dict:
        d = self.model_dump()
        if d["year"] is not None:
            d["year"] = date(d["year"], 1, 1)
        return d


class UserEntryOut(BaseModel):
    id: int
    name: str
    name_type: str
    country_code: str | None
    gender_code: str | None
    year: int | None
    count: int | None
    notes: str | None

    model_config = {"from_attributes": True}

    @field_validator("year", mode="before")
    @classmethod
    def _coerce_year(cls, v):
        return coerce_date_to_year(v)
