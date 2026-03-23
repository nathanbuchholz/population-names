"""Per-source pipeline DAGs.

Generates one DAG per source from the manifest. Each DAG runs:
  retrieve -> promote_converted -> promote_validated -> ingest
  -> dbt_run -> dbt_test -> quality_gate -> dbt_source_freshness -> refresh_views

The refresh_views task produces Asset("pipeline://tables_loaded") to trigger
downstream DAGs (refresh_superset, seed_superset).
"""

import sys
from datetime import datetime
from pathlib import Path

# Airflow 3 is installed in the Docker container, not the local venv
from airflow.providers.standard.operators.bash import (
    BashOperator,  # type: ignore[import-not-found]
)
from airflow.sdk.definitions.asset import Asset  # type: ignore[import-not-found]

from airflow import DAG

DAG_START_DATE = datetime(2026, 3, 1)

# Make pipeline package importable inside Airflow
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.manifest import list_sources
from scripts.ingest import HANDLERS

PROJECT_DIR = "/opt/airflow"
STORE_CMD = f"cd {PROJECT_DIR} && python scripts/store_cli.py"
INGEST_CMD = f"cd {PROJECT_DIR} && python scripts/ingest.py"
QUALITY_CMD = f"cd {PROJECT_DIR} && python scripts/quality_check.py"
FORCE_FLAG = "{% if dag_run.conf.get('force') %} --force{% endif %}"

DBT_DIR = f"{PROJECT_DIR}/dbt_project"

# Shell snippet to export DATABASE_URL_SYNC from PIPELINE_DB_* env vars
DB_URL_EXPORT = (
    'export DATABASE_URL_SYNC="postgresql://$PIPELINE_DB_USER:$PIPELINE_DB_PASSWORD'
    '@$PIPELINE_DB_HOST:$PIPELINE_DB_PORT/$PIPELINE_DB_NAME" && '
)

# Shell snippet to export dbt env vars from PIPELINE_DB_* env vars
DBT_ENV_EXPORT = (
    "export POSTGRES_HOST=$PIPELINE_DB_HOST "
    "POSTGRES_PORT=$PIPELINE_DB_PORT "
    "POSTGRES_USER=$PIPELINE_DB_USER "
    "POSTGRES_PASSWORD=$PIPELINE_DB_PASSWORD "
    "POSTGRES_DB=$PIPELINE_DB_NAME && "
)

PIPELINE_ENV = {
    "DATA_DIR": f"{PROJECT_DIR}/data/validated",
}

TABLES_LOADED = Asset("pipeline://tables_loaded")

default_args = {
    "owner": "pipeline",
    "retries": 2,
}

for source_id in list_sources():
    if source_id not in HANDLERS:
        continue

    dag_id = f"source_{source_id}"

    with DAG(
        dag_id=dag_id,
        default_args=default_args,
        description=f"Pipeline for {source_id}",
        schedule=None,
        start_date=DAG_START_DATE,
        catchup=False,
        tags=["population-names", "source"],
    ) as dag:
        retrieve = BashOperator(
            task_id="retrieve",
            bash_command=f"{STORE_CMD} retrieve --source={source_id}",
        )

        promote_converted = BashOperator(
            task_id="promote_converted",
            bash_command=f"{STORE_CMD} promote --source={source_id} --tier converted",
        )

        promote_validated = BashOperator(
            task_id="promote_validated",
            bash_command=f"{STORE_CMD} promote --source={source_id} --tier validated",
        )

        ingest = BashOperator(
            task_id="ingest",
            bash_command=f"{DB_URL_EXPORT}{INGEST_CMD} --source={source_id} {FORCE_FLAG}",
            env=PIPELINE_ENV,
            append_env=True,
        )

        dbt_run = BashOperator(
            task_id="dbt_run",
            pool="dbt",
            bash_command=(
                f"{DBT_ENV_EXPORT}"
                f"dbt run --select stg_{source_id}+ rej_{source_id} rej_all "
                f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR}"
            ),
        )

        dbt_test = BashOperator(
            task_id="dbt_test",
            pool="dbt",
            bash_command=(
                f"{DBT_ENV_EXPORT}"
                f"dbt test --select stg_{source_id} source:raw.{source_id} "
                f"--exclude assert_raw_tables_not_empty "
                f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR}"
            ),
        )

        quality_gate = BashOperator(
            task_id="quality_gate",
            bash_command=f"{DB_URL_EXPORT}{QUALITY_CMD} --source={source_id}",
            env=PIPELINE_ENV,
            append_env=True,
            skip_on_exit_code=[2],
        )

        dbt_source_freshness = BashOperator(
            task_id="dbt_source_freshness",
            pool="dbt",
            bash_command=(
                f"{DBT_ENV_EXPORT}"
                f"dbt source freshness --select source:raw.{source_id} "
                f"--project-dir {DBT_DIR} --profiles-dir {DBT_DIR}"
            ),
            trigger_rule="none_failed",
        )

        refresh_views = BashOperator(
            task_id="refresh_views",
            pool="dbt",
            bash_command=(
                f"{DB_URL_EXPORT}cd {PROJECT_DIR} && "
                "psql $DATABASE_URL_SYNC -f scripts/refresh_views.sql"
            ),
            outlets=[TABLES_LOADED],
            trigger_rule="none_failed",
        )

        (
            retrieve
            >> promote_converted
            >> promote_validated
            >> ingest
            >> dbt_run
            >> dbt_test
            >> quality_gate
            >> dbt_source_freshness
            >> refresh_views
        )

    # Register DAG in module globals so Airflow discovers it
    globals()[dag_id] = dag
