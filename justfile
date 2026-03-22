# Task runner for the population names pipeline demo

# Max seconds to wait for any single service during setup (override: just --set setup_timeout 300 setup)
setup_timeout := "120"

# Show full command output (override: just verbose=true setup)
verbose := "false"
_q := if verbose == "true" { "" } else { "> /dev/null 2>&1" }

# Generate .env with random secrets
gen-env:
    @echo "Generating .env with random secrets..."
    @python3 -c "\
    import secrets; \
    lines = [ \
        f'POSTGRES_DB=population_names', \
        f'POSTGRES_USER=pipeline', \
        f'POSTGRES_PASSWORD={secrets.token_urlsafe(32)}', \
        f'', \
        f'API_KEY={secrets.token_urlsafe(32)}', \
        f'', \
        f'AIRFLOW_DB_USER=airflow', \
        f'AIRFLOW_DB_NAME=airflow', \
        f'AIRFLOW_DB_PASSWORD={secrets.token_urlsafe(32)}', \
        f'', \
        f'AIRFLOW_FERNET_KEY={secrets.token_urlsafe(32)}', \
        f'AIRFLOW_SECRET_KEY={secrets.token_urlsafe(32)}', \
        f'AIRFLOW_JWT_SECRET={secrets.token_urlsafe(32)}', \
        f'', \
        f'AIRFLOW_ADMIN_USER=admin', \
        f'AIRFLOW_ADMIN_PASSWORD={secrets.token_urlsafe(16)}', \
        f'', \
        f'SUPERSET_DB_USER=superset', \
        f'SUPERSET_DB_NAME=superset', \
        f'SUPERSET_DB_PASSWORD={secrets.token_urlsafe(32)}', \
        f'SUPERSET_SECRET_KEY={secrets.token_urlsafe(42)}', \
        f'', \
        f'SUPERSET_ADMIN_USER=admin', \
        f'SUPERSET_ADMIN_PASSWORD={secrets.token_urlsafe(16)}', \
    ]; \
    open('.env', 'w').write('\n'.join(lines) + '\n'); \
    "
    @echo ".env generated."

# Start all services
up:
    @docker compose rm -f superset-init airflow-init > /dev/null 2>&1 || true
    docker compose up -d

# Stop all services
down:
    docker compose down

# Run Alembic migrations
migrate:
    @docker compose exec -T api uv run alembic upgrade head {{ _q }}

# Download source data from GitHub release (cached)
download:
    @echo "Downloading source data..."
    @uv run python scripts/download_sources.py

# Full setup: clean, start services, wait for health, migrate, run pipeline
setup: clean _ensure-env download _fix-data-perms up
    @echo "Waiting for services to be healthy (timeout: {{ setup_timeout }}s per service)..."
    @just _wait-until "docker compose exec -T db pg_isready -U pipeline -d population_names" "Database"
    @just _wait-until "curl -sf http://localhost:8000/health" "API"
    @echo "Running migrations..."
    @just migrate
    @echo "Migrations complete."
    @echo "Running dbt setup (creates staging views)..."
    @docker compose run --rm -T dbt deps --profiles-dir . {{ _q }}
    @docker compose run --rm -T dbt run --profiles-dir . {{ _q }}
    @echo "dbt setup complete."
    @echo "Creating materialized views and indexes..."
    @docker compose exec -T db psql -U pipeline -d population_names < scripts/refresh_views.sql {{ _q }}
    @echo "Materialized views created."
    @echo "Waiting for Airflow to register DAGs..."
    @docker compose exec -T airflow-scheduler airflow dags reserialize {{ _q }} || true
    @if docker compose exec -T airflow-scheduler airflow dags list-import-errors 2>&1 | grep -q "source_"; then \
        echo "ERROR: Source DAGs have import errors:" >&2; \
        docker compose exec -T airflow-scheduler airflow dags list-import-errors 2>&1 >&2; \
        exit 1; \
    fi
    @if ! docker compose exec -T airflow-webserver airflow dags list 2>/dev/null | grep -q trigger_all_sources; then \
        echo "ERROR: DAG 'trigger_all_sources' not found. Check: docker compose logs airflow-scheduler" >&2; \
        exit 1; \
    fi
    @echo "Airflow ready."
    @docker compose exec -T airflow-scheduler airflow dags unpause trigger_all_sources {{ _q }} || true
    @docker compose exec -T airflow-scheduler airflow dags unpause refresh_superset {{ _q }} || true
    @echo "Unpausing source DAGs..."
    @docker compose exec -T airflow-scheduler bash -c 'airflow dags list -o plain 2>/dev/null | grep "^source_" | while read dag rest; do airflow dags unpause "$dag" > /dev/null 2>&1; done' || true
    @just _wait-until "curl -sf http://localhost:8088/health" "Superset"
    @echo "Seeding Superset dashboards..."
    @docker compose exec -T airflow-webserver python /opt/airflow/seed_superset.py
    @echo "Superset seeded."
    @echo "Triggering pipeline..."
    @just pipeline
    @echo "Pipeline triggered."
    @echo ""
    @echo "All services started."
    @echo "  API:      http://localhost:8000/docs"
    @echo "  Airflow:  http://localhost:8080"
    @echo "  Superset: http://localhost:8088"
    @echo "Check Airflow for data processing status."

# Wait for a command to succeed, or fail after setup_timeout seconds
_wait-until cmd label:
    @elapsed=0; \
    while ! {{ cmd }} > /dev/null 2>&1; do \
        elapsed=$((elapsed + 2)); \
        if [ "$elapsed" -ge {{ setup_timeout }} ]; then \
            echo "ERROR: {{ label }} did not become ready within {{ setup_timeout }}s" >&2; \
            exit 1; \
        fi; \
        sleep 2; \
    done; \
    echo "{{ label }} ready."

# Wait for a container to exit, or fail after setup_timeout seconds
_wait-until-exited container label:
    @echo "Waiting for {{ label }}..."
    @elapsed=0; \
    while ! docker compose ps -a {{ container }} --format '{{{{.State}}' 2>/dev/null | grep -qi exited; do \
        elapsed=$((elapsed + 2)); \
        if [ "$elapsed" -ge {{ setup_timeout }} ]; then \
            echo "ERROR: {{ label }} did not finish within {{ setup_timeout }}s" >&2; \
            exit 1; \
        fi; \
        sleep 2; \
    done

# Make mounted dirs writable by Airflow container (runs as UID 50000)
_fix-data-perms:
    @chmod -R a+rwX data/ 2>/dev/null || true
    @chmod -R a+rwX dbt_project/ 2>/dev/null || true

# Generate .env if it doesn't exist
_ensure-env:
    @[ -f .env ] || just gen-env

# Run full pipeline via Airflow (triggers all source pipelines in parallel)
pipeline:
    @docker compose exec -T airflow-webserver airflow dags trigger --conf '{"force": true}' trigger_all_sources {{ _q }}

# File store operations
store-status:
    uv run python scripts/store_cli.py status

store-retrieve:
    uv run python scripts/store_cli.py retrieve --all

store-promote:
    uv run python scripts/store_cli.py promote --all

# dbt commands
dbt-run:
    docker compose run --rm dbt run --profiles-dir .

dbt-test:
    docker compose run --rm dbt test --profiles-dir .

dbt-docs:
    docker compose run --rm -p 8081:8080 dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .

# API tests
test:
    docker compose exec -T api uv run pytest tests/ -v

# Linting
lint:
    uv run ruff check src/ tests/ scripts/ pipeline/

format:
    uv run ruff format src/ tests/ scripts/ pipeline/

# View logs
logs *args:
    docker compose logs -f {{ args }}

# ---------------------------------------------------------------------------
# AWS image validation (run before deploy.sh to catch failures locally)
# ---------------------------------------------------------------------------

# Build the Docker images as deploy.sh would, then verify the ECS startup
# commands work against the local Docker Compose database. If this passes,
# the ECS deploy should work on the first attempt.
test-images: _ensure-env
    @echo "Building API image (as deploy.sh would)..."
    docker build -t api-demo-test:api -f Dockerfile .
    @echo ""
    @echo "Building Airflow image (as deploy.sh would)..."
    docker build -t api-demo-test:airflow -f Dockerfile.airflow .
    @echo ""
    @echo "Checking baked-in files..."
    @echo "  API image:"
    @docker run --rm api-demo-test:api ls alembic.ini alembic/env.py > /dev/null \
        && echo "    alembic/          OK" \
        || (echo "    alembic/          MISSING" && exit 1)
    @echo "  Airflow image:"
    @for f in dags/source_pipelines.py pipeline/manifest.py scripts/ingest.py dbt_project/dbt_project.yml seed_superset.py superset_queries.py; do \
        docker run --rm --entrypoint bash api-demo-test:airflow -c "test -f /opt/airflow/$f" > /dev/null 2>&1 \
            && echo "    $f  OK" \
            || (echo "    $f  MISSING" && exit 1); \
    done
    @echo ""
    @echo "Starting local databases for command tests..."
    @docker compose up -d db airflow-metadata > /dev/null 2>&1
    @just _wait-until "docker compose exec -T db pg_isready -U pipeline -d population_names" "Database"
    @just _wait-until "docker compose exec -T airflow-metadata pg_isready -U airflow -d airflow" "Airflow metadata DB"
    @echo ""
    @echo "Testing API startup command (alembic migrate)..."
    @docker run --rm --network api-demo_default \
        -e DATABASE_URL_SYNC="postgresql://pipeline:`grep POSTGRES_PASSWORD .env | cut -d= -f2`@db:5432/population_names" \
        api-demo-test:api \
        uv run alembic upgrade head
    @echo "  Alembic migrations OK"
    @echo ""
    @echo "Testing Airflow init command (db migrate + connection add)..."
    @docker run --rm --network api-demo_default \
        -e AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="postgresql+psycopg2://`grep AIRFLOW_DB_USER .env | cut -d= -f2`:`grep AIRFLOW_DB_PASSWORD .env | cut -d= -f2`@airflow-metadata:5432/`grep AIRFLOW_DB_NAME .env | cut -d= -f2`" \
        -e AIRFLOW__CORE__EXECUTOR=LocalExecutor \
        -e AIRFLOW__CORE__LOAD_EXAMPLES=false \
        -e PIPELINE_DB_HOST=db -e PIPELINE_DB_PORT=5432 \
        -e PIPELINE_DB_USER=pipeline \
        -e "PIPELINE_DB_PASSWORD=`grep POSTGRES_PASSWORD .env | cut -d= -f2`" \
        -e PIPELINE_DB_NAME=population_names \
        api-demo-test:airflow \
        bash -c "airflow db migrate && airflow connections add pipeline_db --conn-type postgres --conn-host db --conn-port 5432 --conn-login pipeline --conn-password unused --conn-schema population_names || true"
    @echo "  Airflow init OK"
    @echo ""
    @echo "All image tests passed. Safe to run: cd terraform && ./deploy.sh"

# Reset everything (including downloaded source data)
clean:
    docker compose down -v
    @# Data dirs may be owned by Airflow container (UID 50000), use Docker to clean
    @docker run --rm -v "{{justfile_directory()}}/data:/data" alpine rm -rf /data/raw /data/archived /data/converted /data/validated /data/done /data/rejected 2>/dev/null || rm -rf data/raw/ data/archived/ data/converted/ data/validated/ data/done/ data/rejected/
