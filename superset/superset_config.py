"""Superset configuration loaded from environment variables."""

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{os.environ['SUPERSET_DB_USER']}"
    f":{os.environ['SUPERSET_DB_PASSWORD']}"
    f"@superset-metadata:5432/{os.environ['SUPERSET_DB_NAME']}"
)

# Disable features not needed for local demo
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = False
SUPERSET_LOAD_EXAMPLES = False

# Simple in-memory cache
CACHE_CONFIG = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
}
DATA_CACHE_CONFIG = CACHE_CONFIG
