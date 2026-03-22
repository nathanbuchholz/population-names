"""Reference data endpoints for countries."""

from fastapi import APIRouter
from sqlalchemy import select

from src.api.dependencies import APIKeyDep, SessionDep
from src.db.models import Country
from src.schemas.common import CountryOut

router = APIRouter(prefix="/api/v1", tags=["reference"])


@router.get("/countries", response_model=list[CountryOut])
async def list_countries(session: SessionDep, _: APIKeyDep):
    result = await session.execute(select(Country).order_by(Country.name))
    return result.scalars().all()
