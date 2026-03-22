"""Pydantic schemas for pipeline status and DAG trigger responses."""

from pydantic import BaseModel


class PipelineStatus(BaseModel):
    last_run: str | None
    status: str | None
    row_counts: dict[str, int]


class PipelineTriggerResponse(BaseModel):
    message: str
    dag_run_id: str | None = None
