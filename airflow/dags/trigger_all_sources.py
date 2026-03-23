"""Trigger All Sources DAG.

Convenience DAG that triggers all per-source DAGs in parallel.
Supports passthrough of 'force' config.
"""

import sys
from datetime import datetime
from pathlib import Path

# Airflow 3 is installed in the Docker container, not the local venv
from airflow.providers.standard.operators.trigger_dagrun import (
    TriggerDagRunOperator,  # type: ignore[import-not-found]
)

from airflow import DAG

DAG_START_DATE = datetime(2026, 3, 1)

# Make pipeline package importable inside Airflow
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.manifest import list_sources
from scripts.ingest import HANDLERS

default_args = {
    "owner": "pipeline",
    "retries": 0,
}

with DAG(
    dag_id="trigger_all_sources",
    default_args=default_args,
    description="Trigger all per-source pipelines in parallel",
    schedule=None,
    start_date=DAG_START_DATE,
    catchup=False,
    tags=["population-names", "orchestration"],
) as dag:
    for source_id in list_sources():
        if source_id not in HANDLERS:
            continue

        TriggerDagRunOperator(
            task_id=f"trigger_{source_id}",
            trigger_dag_id=f"source_{source_id}",
            conf={"force": "{{ dag_run.conf.get('force', False) }}"},
            wait_for_completion=False,
        )
