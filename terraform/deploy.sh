#!/usr/bin/env bash
# Deploy script: build images, push to ECR, apply Terraform, run migrations.
#
# Usage:
#   cd terraform
#   ./deploy.sh          # Full deploy (init + plan + apply + push images)
#   ./deploy.sh plan     # Just plan
#   ./deploy.sh destroy  # Tear everything down

set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "==> $*"; }

get_output() {
  terraform output -raw "$1" 2>/dev/null
}

ecr_login() {
  local account_id
  account_id=$(aws sts get-caller-identity --query Account --output text)
  aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "${account_id}.dkr.ecr.${REGION}.amazonaws.com"
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
case "${1:-apply}" in
  validate)
    terraform init -upgrade
    terraform validate
    log "Terraform config is valid."
    ;;

  plan)
    terraform init -upgrade
    terraform plan
    ;;

  apply)
    log "Initialising Terraform..."
    terraform init -upgrade

    log "Validating..."
    terraform validate

    log "Planning..."
    terraform plan -out=tfplan

    read -rp "Apply this plan? [y/N] " confirm
    if [[ "$confirm" != [yY] ]]; then
      echo "Aborted."
      rm -f tfplan
      exit 0
    fi

    log "Applying..."
    terraform apply tfplan
    rm -f tfplan

    log "Logging in to ECR..."
    ecr_login

    API_REPO=$(get_output ecr_api_repo)
    AIRFLOW_REPO=$(get_output ecr_airflow_repo)

    log "Building and pushing API image..."
    docker build -t "${API_REPO}:latest" -f "$PROJECT_DIR/Dockerfile" "$PROJECT_DIR"
    docker push "${API_REPO}:latest"

    log "Building and pushing Airflow image..."
    docker build -t "${AIRFLOW_REPO}:latest" -f "$PROJECT_DIR/Dockerfile.airflow" "$PROJECT_DIR"
    docker push "${AIRFLOW_REPO}:latest"

    log "Forcing ECS service redeployment..."
    CLUSTER=$(get_output ecs_cluster_name)
    PREFIX=$(terraform output -raw ecs_cluster_name | sed 's/-cluster$//')
    for svc in api airflow-web airflow-sched superset; do
      aws ecs update-service \
        --cluster "$CLUSTER" \
        --service "${PREFIX}-${svc}" \
        --force-new-deployment \
        --region "$REGION" \
        --no-cli-pager 2>/dev/null || true
    done

    log "Deploy complete!"
    echo ""
    echo "  API:      $(get_output api_url)"
    echo "  Airflow:  $(get_output airflow_url)"
    echo "  Superset: $(get_output superset_url)"
    echo ""
    echo "  ECR API:     $(get_output ecr_api_repo)"
    echo "  ECR Airflow: $(get_output ecr_airflow_repo)"
    echo "  S3 Data:     $(get_output s3_data_bucket)"
    echo ""
    echo "  REMINDER: Resources cost ~\$0.17/hr while running."
    echo "  Run ./deploy.sh destroy when done."
    ;;

  destroy)
    log "Destroying all resources..."
    terraform destroy
    ;;

  *)
    echo "Usage: $0 [validate|plan|apply|destroy]"
    exit 1
    ;;
esac
