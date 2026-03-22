"""FastAPI dependencies for database sessions and API key auth."""

from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_api_key(key: str = Security(api_key_header)) -> str:
    if key != settings.api_key:
        raise HTTPException(403, "Invalid API key")
    return key


APIKeyDep = Annotated[str, Depends(verify_api_key)]
