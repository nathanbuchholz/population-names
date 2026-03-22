"""Pipeline trigger and status endpoints (delegates to Airflow API)."""

import logging

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from src.api.config import settings
from src.api.dependencies import APIKeyDep, SessionDep
from src.schemas.pipeline import PipelineStatus, PipelineTriggerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

DAG_ID = "trigger_all_sources"
AIRFLOW_API = f"{settings.airflow_base_url}/api/v2"

PIPELINE_TABLES: frozenset[str] = frozenset(
    {
        "raw.ssa_forenames",
        "raw.ons_forenames",
        "raw.nrs_forenames",
        "raw.nisra_forenames",
        "raw.wales_forenames",
        "raw.cso_forenames_boys",
        "raw.cso_forenames_girls",
        "raw.census_surnames",
        "raw.england_surnames",
        "raw.nrs_surnames",
        "raw.cso_surnames",
        "raw.ni_surnames",
        "raw.wales_surnames",
        "public.forenames",
        "public.surnames",
    }
)


async def _airflow_token(client: httpx.AsyncClient) -> str:
    """Get a JWT token from Airflow 3's auth endpoint."""
    resp = await client.post(
        f"{settings.airflow_base_url}/auth/token",
        json={"username": settings.airflow_username, "password": settings.airflow_password},
        timeout=5.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _airflow_headers(client: httpx.AsyncClient) -> dict[str, str]:
    token = await _airflow_token(client)
    return {"Authorization": f"Bearer {token}"}


@router.get("/status", response_model=PipelineStatus)
async def pipeline_status(session: SessionDep, _: APIKeyDep):
    row_counts: dict[str, int] = {}
    for table in sorted(PIPELINE_TABLES):
        try:
            result = await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608 - table from PIPELINE_TABLES allowlist
            row_counts[table] = result.scalar_one()
        except Exception:
            logger.warning("Failed to get row count for %s", table, exc_info=True)
            row_counts[table] = 0

    # Try to get last DAG run from Airflow API
    last_run = None
    status = None
    try:
        async with httpx.AsyncClient() as client:
            headers = await _airflow_headers(client)
            resp = await client.get(
                f"{AIRFLOW_API}/dags/{DAG_ID}/dagRuns",
                headers=headers,
                params={"limit": 1, "order_by": "-run_after"},
                timeout=5.0,
            )
            if resp.status_code == 200:
                runs = resp.json().get("dag_runs", [])
                if runs:
                    last_run = runs[0].get("logical_date") or runs[0].get("run_after")
                    status = runs[0].get("state")
    except Exception:
        logger.warning("Failed to fetch Airflow DAG run status", exc_info=True)

    return PipelineStatus(last_run=last_run, status=status, row_counts=row_counts)


@router.post("/run", response_model=PipelineTriggerResponse)
async def trigger_pipeline(_: APIKeyDep):
    try:
        async with httpx.AsyncClient() as client:
            headers = await _airflow_headers(client)
            resp = await client.post(
                f"{AIRFLOW_API}/dags/{DAG_ID}/dagRuns",
                headers=headers,
                json={"logical_date": None, "conf": {}},
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return PipelineTriggerResponse(
                    message="Pipeline triggered", dag_run_id=data.get("dag_run_id")
                )
            raise HTTPException(502, f"Airflow returned {resp.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Could not reach Airflow: {e}")
