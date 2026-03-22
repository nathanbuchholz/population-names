# ---------------------------------------------------------------------------
# ECS Cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${local.name_prefix}-cluster" }
}

# ---------------------------------------------------------------------------
# Service discovery namespace (so containers can resolve each other)
# ---------------------------------------------------------------------------

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${local.name_prefix}.local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "airflow_webserver" {
  name = "airflow-webserver"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------

# --- API ---
resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name_prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = local.api_image
    essential = true

    portMappings = [{ containerPort = 8000, protocol = "tcp" }]

    environment = [
      { name = "DATABASE_URL", value = local.pipeline_db_url_async },
      { name = "DATABASE_URL_SYNC", value = local.pipeline_db_url },
    ]

    secrets = [
      {
        name      = "API_KEY"
        valueFrom = "${aws_secretsmanager_secret.app.arn}:api_key::"
      },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

# --- Airflow webserver ---
resource "aws_ecs_task_definition" "airflow_webserver" {
  family                   = "${local.name_prefix}-airflow-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.airflow_cpu
  memory                   = var.airflow_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "airflow-webserver"
    image     = local.airflow_image
    essential = true
    command = [
      "/bin/bash", "-c",
      join(" && ", [
        "airflow db migrate",
        "airflow connections add pipeline_db --conn-type postgres --conn-host $PIPELINE_DB_HOST --conn-port $PIPELINE_DB_PORT --conn-login $PIPELINE_DB_USER --conn-password $PIPELINE_DB_PASSWORD --conn-schema $PIPELINE_DB_NAME || true",
        "exec airflow api-server"
      ])
    ]

    portMappings = [{ containerPort = 8080, protocol = "tcp" }]

    environment = [
      { name = "AIRFLOW__CORE__EXECUTOR", value = "LocalExecutor" },
      { name = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", value = local.airflow_db_url },
      { name = "AIRFLOW__CORE__LOAD_EXAMPLES", value = "false" },
      { name = "AIRFLOW__CORE__EXECUTION_API_SERVER_URL", value = "http://airflow-webserver.${local.name_prefix}.local:8080/execution/" },
      { name = "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS", value = "true" },
      { name = "DBT_USE_COLORS", value = "False" },
      { name = "PIPELINE_DB_HOST", value = local.db_host },
      { name = "PIPELINE_DB_PORT", value = tostring(local.db_port) },
      { name = "PIPELINE_DB_USER", value = var.db_username },
      { name = "PIPELINE_DB_NAME", value = var.db_name },
      { name = "DATA_BUCKET", value = aws_s3_bucket.data.id },
      # dbt profiles.yml reads POSTGRES_* env vars
      { name = "POSTGRES_HOST", value = local.db_host },
      { name = "POSTGRES_PORT", value = tostring(local.db_port) },
      { name = "POSTGRES_USER", value = var.db_username },
      { name = "POSTGRES_DB", value = var.db_name },
      # seed_superset.py reads SUPERSET_URL
      { name = "SUPERSET_URL", value = "http://${aws_lb.main.dns_name}:8088" },
    ]

    secrets = [
      { name = "AIRFLOW__CORE__FERNET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_fernet_key::" },
      { name = "AIRFLOW__API__SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_secret_key::" },
      { name = "AIRFLOW__API_AUTH__JWT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_jwt_secret::" },
      { name = "PIPELINE_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:db_password::" },
      { name = "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_admin_users::" },
      { name = "POSTGRES_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:db_password::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.airflow_webserver.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "webserver"
      }
    }
  }])
}

# --- Airflow scheduler ---
resource "aws_ecs_task_definition" "airflow_scheduler" {
  family                   = "${local.name_prefix}-airflow-sched"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.airflow_cpu
  memory                   = var.airflow_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "airflow-scheduler"
    image     = local.airflow_image
    essential = true
    command   = ["scheduler"]

    environment = [
      { name = "AIRFLOW__CORE__EXECUTOR", value = "LocalExecutor" },
      { name = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", value = local.airflow_db_url },
      { name = "AIRFLOW__CORE__LOAD_EXAMPLES", value = "false" },
      { name = "AIRFLOW__CORE__EXECUTION_API_SERVER_URL", value = "http://airflow-webserver.${local.name_prefix}.local:8080/execution/" },
      { name = "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS", value = "true" },
      { name = "DBT_USE_COLORS", value = "False" },
      { name = "PIPELINE_DB_HOST", value = local.db_host },
      { name = "PIPELINE_DB_PORT", value = tostring(local.db_port) },
      { name = "PIPELINE_DB_USER", value = var.db_username },
      { name = "PIPELINE_DB_NAME", value = var.db_name },
      { name = "DATA_BUCKET", value = aws_s3_bucket.data.id },
      { name = "POSTGRES_HOST", value = local.db_host },
      { name = "POSTGRES_PORT", value = tostring(local.db_port) },
      { name = "POSTGRES_USER", value = var.db_username },
      { name = "POSTGRES_DB", value = var.db_name },
      { name = "SUPERSET_URL", value = "http://${aws_lb.main.dns_name}:8088" },
    ]

    secrets = [
      { name = "AIRFLOW__CORE__FERNET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_fernet_key::" },
      { name = "AIRFLOW__API__SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_secret_key::" },
      { name = "AIRFLOW__API_AUTH__JWT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_jwt_secret::" },
      { name = "PIPELINE_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:db_password::" },
      { name = "AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS", valueFrom = "${aws_secretsmanager_secret.app.arn}:airflow_admin_users::" },
      { name = "POSTGRES_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:db_password::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.airflow_scheduler.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "scheduler"
      }
    }
  }])
}

# --- Superset ---
resource "aws_ecs_task_definition" "superset" {
  family                   = "${local.name_prefix}-superset"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.superset_cpu
  memory                   = var.superset_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "superset"
    image     = var.superset_image
    essential = true
    user      = "0"

    command = [
      "/bin/bash", "-c",
      join(" && ", [
        "uv pip install psycopg2-binary --python /app/.venv/bin/python",
        "(cat > /app/superset_config.py << 'PYEOF'\nimport os\n\nSECRET_KEY = os.environ[\"SUPERSET_SECRET_KEY\"]\n\nSQLALCHEMY_DATABASE_URI = (\n    f\"postgresql+psycopg2://{os.environ['SUPERSET_DB_USER']}\"\n    f\":{os.environ['SUPERSET_DB_PASSWORD']}\"\n    f\"@{os.environ['SUPERSET_DB_HOST']}:{os.environ['SUPERSET_DB_PORT']}/{os.environ['SUPERSET_DB_NAME']}\"\n)\n\nTALISMAN_ENABLED = False\nWTF_CSRF_ENABLED = False\nSUPERSET_LOAD_EXAMPLES = False\n\nCACHE_CONFIG = {\"CACHE_TYPE\": \"SimpleCache\", \"CACHE_DEFAULT_TIMEOUT\": 300}\nDATA_CACHE_CONFIG = CACHE_CONFIG\nPYEOF\n)",
        "superset db upgrade",
        "superset fab create-admin --username \"$SUPERSET_ADMIN_USER\" --firstname Admin --lastname User --email admin@localhost --password \"$SUPERSET_ADMIN_PASSWORD\" || true",
        "superset init",
        "superset set-database-uri -d 'Population Names' -u \"postgresql+psycopg2://$PIPELINE_DB_USER:$PIPELINE_DB_PASSWORD@$PIPELINE_DB_HOST:$PIPELINE_DB_PORT/$PIPELINE_DB_NAME\" || true",
        "gunicorn --bind 0.0.0.0:8088 --workers 2 --timeout 120 'superset.app:create_app()'"
      ])
    ]

    portMappings = [{ containerPort = 8088, protocol = "tcp" }]

    environment = [
      { name = "SUPERSET_CONFIG_PATH", value = "/app/superset_config.py" },
      { name = "SUPERSET_DB_USER", value = local.superset_db_user },
      { name = "SUPERSET_DB_NAME", value = "superset" },
      { name = "SUPERSET_DB_HOST", value = local.db_host },
      { name = "SUPERSET_DB_PORT", value = tostring(local.db_port) },
      { name = "SUPERSET_ADMIN_USER", value = "admin" },
      { name = "PIPELINE_DB_USER", value = var.db_username },
      { name = "PIPELINE_DB_HOST", value = local.db_host },
      { name = "PIPELINE_DB_PORT", value = tostring(local.db_port) },
      { name = "PIPELINE_DB_NAME", value = var.db_name },
    ]

    secrets = [
      { name = "SUPERSET_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:superset_secret_key::" },
      { name = "SUPERSET_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:superset_db_password::" },
      { name = "SUPERSET_ADMIN_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:superset_admin_password::" },
      { name = "PIPELINE_DB_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:db_password::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.superset.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "superset"
      }
    }
  }])
}

# ---------------------------------------------------------------------------
# ECS Services
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "${local.name_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.api]
}

resource "aws_ecs_service" "airflow_webserver" {
  name            = "${local.name_prefix}-airflow-web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.airflow_webserver.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.airflow.arn
    container_name   = "airflow-webserver"
    container_port   = 8080
  }

  service_registries {
    registry_arn = aws_service_discovery_service.airflow_webserver.arn
  }

  depends_on = [aws_lb_listener.airflow]
}

resource "aws_ecs_service" "airflow_scheduler" {
  name            = "${local.name_prefix}-airflow-sched"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.airflow_scheduler.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }
}

resource "aws_ecs_service" "superset" {
  name            = "${local.name_prefix}-superset"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.superset.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.ecs.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.superset.arn
    container_name   = "superset"
    container_port   = 8088
  }

  depends_on = [aws_lb_listener.superset]
}
