"""Health check endpoint with database connectivity status."""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from src.api.dependencies import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(session: SessionDep) -> dict:
    try:
        await session.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        db_status = "unhealthy"
    return {"status": "ok", "database": db_status}
