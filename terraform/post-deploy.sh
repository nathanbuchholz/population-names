#!/usr/bin/env bash
# Post-deploy setup: runs the steps that `just setup` does locally but that
# deploy.sh does not cover. Uses one-shot ECS Fargate tasks with command
# overrides so no SSH/exec infrastructure is needed.
#
# Usage:
#   cd terraform
#   ./post-deploy.sh          # Run all steps
#   ./post-deploy.sh migrate  # Run only Alembic migrations
#   ./post-deploy.sh dbt      # Run only dbt
#   ./post-deploy.sh views    # Run only materialized views
#   ./post-deploy.sh unpause  # Run only DAG unpause
#   ./post-deploy.sh seed     # Run only Superset seeding
#   ./post-deploy.sh trigger  # Run only pipeline trigger

set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Read Terraform outputs
# ---------------------------------------------------------------------------
out() { terraform output -raw "$1" 2>/dev/null; }

CLUSTER=$(out ecs_cluster_name)
SUBNETS=$(out private_subnets)
SG=$(out ecs_security_group)
PREFIX=$(echo "$CLUSTER" | sed 's/-cluster$//')

log() { echo "==> $*"; }

# ---------------------------------------------------------------------------
# run_task: launch a one-shot Fargate task, wait for it, check exit code
# ---------------------------------------------------------------------------
run_task() {
  local task_def="$1"
  local container="$2"
  local description="$3"
  shift 3
  # remaining args are the command as a JSON array, e.g. '"/bin/bash","-c","..."'
  local cmd_json="$*"

  log "$description"

  local task_arn
  task_arn=$(aws ecs run-task \
    --cluster "$CLUSTER" \
    --task-definition "$task_def" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG]}" \
    --overrides "{\"containerOverrides\":[{\"name\":\"$container\",\"command\":[$cmd_json]}]}" \
    --region "$REGION" \
    --query 'tasks[0].taskArn' \
    --output text)

  echo "    Task: $task_arn"

  aws ecs wait tasks-stopped \
    --cluster "$CLUSTER" \
    --tasks "$task_arn" \
    --region "$REGION"

  local exit_code
  exit_code=$(aws ecs describe-tasks \
    --cluster "$CLUSTER" \
    --tasks "$task_arn" \
    --region "$REGION" \
    --query 'tasks[0].containers[?name==`'"$container"'`].exitCode | [0]' \
    --output text)

  if [ "$exit_code" != "0" ]; then
    echo "    FAILED (exit code $exit_code). Check CloudWatch logs."
    return 1
  fi
  echo "    Done."
}

# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

step_migrate() {
  run_task "${PREFIX}-api" "api" "Running Alembic migrations..." \
    '"/bin/bash","-c","uv run alembic upgrade head"'
}

step_dbt() {
  run_task "${PREFIX}-airflow-web" "airflow-webserver" "Running dbt deps + run..." \
    '"/bin/bash","-c","cd /opt/airflow/dbt_project && dbt deps --profiles-dir . && dbt run --profiles-dir ."'
}

step_views() {
  # Use psycopg2 (available in the Airflow image) to run the SQL file
  run_task "${PREFIX}-airflow-web" "airflow-webserver" "Creating materialized views..." \
    '"/bin/bash","-c","python -c \"import psycopg2, os; conn = psycopg2.connect(host=os.environ[\\\"PIPELINE_DB_HOST\\\"], port=os.environ[\\\"PIPELINE_DB_PORT\\\"], user=os.environ[\\\"PIPELINE_DB_USER\\\"], password=os.environ[\\\"PIPELINE_DB_PASSWORD\\\"], dbname=os.environ[\\\"PIPELINE_DB_NAME\\\"]); conn.autocommit = True; conn.cursor().execute(open(\\\"scripts/refresh_views.sql\\\").read()); conn.close(); print(\\\"Views created.\\\")\""'
}

step_unpause() {
  run_task "${PREFIX}-airflow-web" "airflow-webserver" "Unpausing DAGs..." \
    '"/bin/bash","-c","airflow dags unpause trigger_all_sources && airflow dags unpause refresh_superset && airflow dags list -o plain 2>/dev/null | grep ^source_ | while read dag rest; do airflow dags unpause \"$dag\"; done"'
}

step_seed() {
  run_task "${PREFIX}-airflow-web" "airflow-webserver" "Seeding Superset dashboards..." \
    '"/bin/bash","-c","cd /opt/airflow && python seed_superset.py"'
}

step_trigger() {
  run_task "${PREFIX}-airflow-web" "airflow-webserver" "Triggering pipeline..." \
    '"/bin/bash","-c","airflow dags trigger --conf {\"force\":true} trigger_all_sources"'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "${1:-all}" in
  all)
    step_migrate
    step_dbt
    step_views
    step_unpause
    step_seed
    step_trigger
    log "Post-deploy setup complete."
    echo ""
    echo "  API:      $(out api_url)/docs"
    echo "  Airflow:  $(out airflow_url)"
    echo "  Superset: $(out superset_url)"
    ;;
  migrate)  step_migrate ;;
  dbt)      step_dbt ;;
  views)    step_views ;;
  unpause)  step_unpause ;;
  seed)     step_seed ;;
  trigger)  step_trigger ;;
  *)
    echo "Usage: $0 [all|migrate|dbt|views|unpause|seed|trigger]"
    exit 1
    ;;
esac
