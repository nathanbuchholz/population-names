#!/bin/bash
set -euo pipefail

echo "Installing psycopg2-binary..."
uv pip install psycopg2-binary --python /app/.venv/bin/python

echo "Running Superset DB migrations..."
superset db upgrade

echo "Creating admin user..."
superset fab create-admin \
  --username "${SUPERSET_ADMIN_USER}" \
  --firstname Admin \
  --lastname User \
  --email admin@localhost \
  --password "${SUPERSET_ADMIN_PASSWORD}"

echo "Initialising roles and permissions..."
superset init

echo "Adding Population Names database connection..."
superset set-database-uri \
  -d "Population Names" \
  -u "postgresql+psycopg2://${PIPELINE_DB_USER}:${PIPELINE_DB_PASSWORD}@db:5432/${PIPELINE_DB_NAME}"

echo "Superset init complete."
