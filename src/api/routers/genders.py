"""Reference data endpoints for genders."""

from fastapi import APIRouter
from sqlalchemy import select

from src.api.dependencies import APIKeyDep, SessionDep
from src.db.models import Gender
from src.schemas.common import GenderOut

router = APIRouter(prefix="/api/v1", tags=["reference"])


@router.get("/genders", response_model=list[GenderOut])
async def list_genders(session: SessionDep, _: APIKeyDep):
    result = await session.execute(select(Gender).order_by(Gender.code))
    return result.scalars().all()
