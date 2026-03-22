"""FastAPI application setup, middleware, and router registration."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.api.config import settings
from src.api.routers import analytics, countries, genders, health, names, pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Population Names API",
    description="Explore name popularity across the US and UK",
    version="0.1.0",
)

cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/scalar", include_in_schema=False)
async def scalar_docs() -> HTMLResponse:
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head><title>Population Names API - Scalar</title><meta charset="utf-8" /></head>
<body>
  <script id="api-reference" data-url="/openapi.json"></script>
  <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>
""")


app.include_router(health.router)
app.include_router(countries.router)
app.include_router(genders.router)
app.include_router(names.router)
app.include_router(analytics.router)
app.include_router(pipeline.router)
