"""SQLAlchemy ORM models for countries, genders, forenames, surnames, and rankings."""

import datetime

from sqlalchemy import Date, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Country(Base):
    __tablename__ = "countries"

    country_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    iso_alpha2: Mapped[str] = mapped_column(Text, nullable=False)
    iso_alpha3: Mapped[str] = mapped_column(Text, nullable=False)
    subdivision_code: Mapped[str | None] = mapped_column(Text, unique=True)


class Gender(Base):
    __tablename__ = "genders"

    gender_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(1), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)


class Forename(Base):
    __tablename__ = "forenames"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    gender_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class Surname(Base):
    __tablename__ = "surnames"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    country_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


# Materialized views - read-only models for SQLAlchemy queries


class MvForenameRanking(Base):
    __tablename__ = "mv_forename_rankings"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    gender_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    pct_of_year_total: Mapped[float | None] = mapped_column(Numeric)


class MvSurnameRanking(Base):
    __tablename__ = "mv_surname_rankings"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    country_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    pct_of_year_total: Mapped[float | None] = mapped_column(Numeric)


class UserNameEntry(Base):
    __tablename__ = "user_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_type: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    gender_code: Mapped[str | None] = mapped_column(String(1))
    year: Mapped[datetime.date | None] = mapped_column(Date)
    count: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
