"""Refresh Superset Cache DAG.

Triggered by Asset("pipeline://tables_loaded") after source pipelines refresh MVs.
Warms up Superset chart caches so dashboards render immediately.
"""

import json
import logging
import os
import urllib.error
import urllib.request

# Airflow 3 is installed in the Docker container, not the local venv
from airflow.providers.standard.operators.python import PythonOperator  # type: ignore[import-not-found]
from airflow.sdk.definitions.asset import Asset  # type: ignore[import-not-found]

from airflow import DAG
from dag_config import DAG_START_DATE

logger = logging.getLogger(__name__)

TABLES_LOADED = Asset("pipeline://tables_loaded")

SUPERSET_URL = "http://superset:8088"


def warm_superset_cache():
    """Log in to Superset and warm up all chart caches."""
    username = os.environ.get("SUPERSET_ADMIN_USER", "admin")
    password = os.environ["SUPERSET_ADMIN_PASSWORD"]

    # Login
    login_body = json.dumps({
        "username": username,
        "password": password,
        "provider": "db",
    }).encode()
    req = urllib.request.Request(
        f"{SUPERSET_URL}/api/v1/security/login",
        data=login_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read())["access_token"]

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # List all charts
    req = urllib.request.Request(
        f"{SUPERSET_URL}/api/v1/chart/?page_size=1000",
        headers=auth_headers,
    )
    with urllib.request.urlopen(req) as resp:
        charts = json.loads(resp.read()).get("result", [])

    if not charts:
        logger.info("No charts found in Superset - skipping cache warm-up.")
        return

    # Warm up each chart's cache (1 retry with 2s delay)
    for chart in charts:
        chart_id = chart["id"]
        body = json.dumps({"chart_id": chart_id}).encode()
        for attempt in range(2):
            req = urllib.request.Request(
                f"{SUPERSET_URL}/api/v1/chart/warm_up_cache",
                data=body,
                headers=auth_headers,
                method="PUT",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    logger.debug("Warmed cache for chart %s: %s", chart_id, resp.status)
                break
            except urllib.error.HTTPError as e:
                if attempt == 0:
                    logger.warning(
                        "Cache warm-up failed for chart %s: %s, retrying...", chart_id, e,
                    )
                    import time
                    time.sleep(2)
                else:
                    logger.error("Cache warm-up failed for chart %s after retry: %s", chart_id, e)

    logger.info("Cache warm-up complete for %d chart(s).", len(charts))


with DAG(
    dag_id="refresh_superset",
    description="Warm Superset chart caches after views are refreshed",
    schedule=[TABLES_LOADED],
    start_date=DAG_START_DATE,
    catchup=False,
    is_paused_upon_creation=False,
    tags=["population-names", "post-pipeline", "superset"],
) as dag:

    warm_cache = PythonOperator(
        task_id="warm_superset_cache",
        python_callable=warm_superset_cache,
    )
