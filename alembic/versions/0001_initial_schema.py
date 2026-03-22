"""
Revision ID: 0001
Revises:
Create Date: 2026-03-09 00:00:00.000000

Initial schema: raw, staging, and public schemas with raw tables, dimension
tables, and seed data. Public forenames/surnames are materialized views
created by scripts/refresh_views.sql after dbt runs.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw")
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE SCHEMA IF NOT EXISTS rejected")

    # raw.file_log - one row per file per ingestion
    op.create_table(
        "file_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("file_hash", sa.Text),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column(
            "status",
            sa.Text,
            sa.CheckConstraint("status IN ('success', 'failed', 'rejected')"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("forced", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema="raw",
    )
    op.create_index(
        "idx_file_log_source_status",
        "file_log",
        ["source_id", "status", sa.text("started_at DESC")],
        schema="raw",
    )

    # public.countries
    op.create_table(
        "countries",
        sa.Column("country_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("iso_alpha2", sa.Text, nullable=False),
        sa.Column("iso_alpha3", sa.Text, nullable=False),
        sa.Column("subdivision_code", sa.Text, unique=True),
        sa.Column("population", sa.BigInteger),
        schema="public",
    )

    # public.genders
    op.create_table(
        "genders",
        sa.Column("gender_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(1), unique=True, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        schema="public",
    )

    # public.user_entries
    op.create_table(
        "user_entries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("name_type", sa.Text, nullable=False),
        sa.Column("country_code", sa.Text),
        sa.Column("gender_code", sa.String(1)),
        sa.Column("year", sa.Date),
        sa.Column("count", sa.Integer),
        sa.Column("notes", sa.Text),
        schema="public",
    )

    # raw tables - forenames with shared structure
    for table_name in [
        "ssa_forenames",
        "ons_forenames",
        "nrs_forenames",
        "nisra_forenames",
        "wales_forenames",
    ]:
        cols = [
            sa.Column("name", sa.Text),
            sa.Column("sex", sa.Text),
            sa.Column("count", sa.Text),
        ]
        if table_name != "ssa_forenames":
            cols.append(sa.Column("rank", sa.Text))
        cols.extend(
            [
                sa.Column("year", sa.Text),
                sa.Column("file_log_id", sa.BigInteger),
                sa.Column(
                    "_loaded_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("NOW()"),
                ),
            ]
        )
        op.create_table(table_name, *cols, schema="raw")

    # raw.census_surnames
    op.create_table(
        "census_surnames",
        sa.Column("name", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.england_surnames
    op.create_table(
        "england_surnames",
        sa.Column("name", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.nrs_surnames
    op.create_table(
        "nrs_surnames",
        sa.Column("name", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("rank", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.cso_forenames_boys
    op.create_table(
        "cso_forenames_boys",
        sa.Column("name", sa.Text),
        sa.Column("sex", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("rank", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.cso_forenames_girls
    op.create_table(
        "cso_forenames_girls",
        sa.Column("name", sa.Text),
        sa.Column("sex", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("rank", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.cso_surnames
    op.create_table(
        "cso_surnames",
        sa.Column("name", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("rank", sa.Text),
        sa.Column("year", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.ni_surnames
    op.create_table(
        "ni_surnames",
        sa.Column("name", sa.Text),
        sa.Column("origin", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # raw.wales_surnames
    op.create_table(
        "wales_surnames",
        sa.Column("name", sa.Text),
        sa.Column("rank", sa.Text),
        sa.Column("count", sa.Text),
        sa.Column("origin", sa.Text),
        sa.Column("file_log_id", sa.BigInteger),
        sa.Column("_loaded_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        schema="raw",
    )

    # Seed metadata
    op.execute("""
        INSERT INTO public.genders (code, label) VALUES
            ('F', 'Female'),
            ('M', 'Male')
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO public.countries (name, iso_alpha2, iso_alpha3, subdivision_code, population) VALUES
            ('United States', 'US', 'USA', NULL, 340100000),
            ('England', 'GB', 'GBR', 'GB-ENG', 58620000),
            ('Wales', 'GB', 'GBR', 'GB-WLS', 3190000),
            ('Scotland', 'GB', 'GBR', 'GB-SCT', 5550000),
            ('Northern Ireland', 'GB', 'GBR', 'GB-NIR', 1930000)
        ON CONFLICT (subdivision_code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO public.countries (name, iso_alpha2, iso_alpha3, subdivision_code, population)
        SELECT 'United States', 'US', 'USA', NULL, 340100000
        WHERE NOT EXISTS (SELECT 1 FROM public.countries WHERE name = 'United States')
    """)
    op.execute("""
        INSERT INTO public.countries (name, iso_alpha2, iso_alpha3, subdivision_code, population)
        SELECT 'Ireland', 'IE', 'IRL', NULL, 5380000
        WHERE NOT EXISTS (SELECT 1 FROM public.countries WHERE name = 'Ireland')
    """)


def downgrade() -> None:
    for table in [
        "wales_surnames",
        "ni_surnames",
        "cso_surnames",
        "cso_forenames_girls",
        "cso_forenames_boys",
        "nrs_surnames",
        "england_surnames",
        "census_surnames",
        "wales_forenames",
        "nisra_forenames",
        "nrs_forenames",
        "ons_forenames",
        "ssa_forenames",
    ]:
        op.drop_table(table, schema="raw")

    op.drop_table("user_entries", schema="public")
    op.drop_table("genders", schema="public")
    op.drop_table("countries", schema="public")

    op.drop_index("idx_file_log_source_status", table_name="file_log", schema="raw")
    op.drop_table("file_log", schema="raw")

    op.execute("DROP SCHEMA IF EXISTS rejected")
    op.execute("DROP SCHEMA IF EXISTS staging")
    op.execute("DROP SCHEMA IF EXISTS raw")
