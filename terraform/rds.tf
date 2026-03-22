# ---------------------------------------------------------------------------
# RDS PostgreSQL - single instance hosting all three databases (POC tradeoff)
# (population_names, airflow, superset)
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${local.name_prefix}-db-subnet-group" }
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-pg"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 2
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_master.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az            = false # POC
  publicly_accessible = false
  skip_final_snapshot = true # POC
  deletion_protection = false

  backup_retention_period = 1
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  parameter_group_name = aws_db_parameter_group.main.name

  tags = { Name = "${local.name_prefix}-pg" }
}

resource "aws_db_parameter_group" "main" {
  name_prefix = "${local.name_prefix}-pg16-"
  family      = "postgres16"
  description = "PostgreSQL 16 parameters for ${var.project}"

  parameter {
    name  = "jit"
    value = "off"
  }

  lifecycle { create_before_destroy = true }
}

# ---------------------------------------------------------------------------
# Bootstrap: create additional databases + roles via Lambda in VPC
# (runs once after RDS is created -- Lambda can reach private RDS)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "db_bootstrap" {
  name               = "${local.name_prefix}-db-bootstrap"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "db_bootstrap_vpc" {
  role       = aws_iam_role.db_bootstrap.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Build the Lambda package with pg8000 (pure-Python PostgreSQL driver, no
# native compilation needed).
resource "terraform_data" "build_lambda" {
  triggers_replace = [timestamp()]

  provisioner "local-exec" {
    command = <<-EOT
      rm -rf "${path.module}/.build/lambda"
      mkdir -p "${path.module}/.build/lambda"
      pip install --target "${path.module}/.build/lambda" pg8000 --quiet
    EOT
  }
}

data "archive_file" "db_bootstrap" {
  type        = "zip"
  output_path = "${path.module}/.build/db_bootstrap.zip"
  source_dir  = "${path.module}/.build/lambda"

  depends_on = [terraform_data.build_lambda, local_file.db_bootstrap_handler]
}

resource "local_file" "db_bootstrap_handler" {
  filename = "${path.module}/.build/lambda/index.py"
  content  = <<-PYTHON
import os
import pg8000.dbapi


def handler(event, context):
    conn = pg8000.dbapi.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    for role, password, dbname in [
        (os.environ["AIRFLOW_DB_USER"], os.environ["AIRFLOW_DB_PASSWORD"], "airflow"),
        (os.environ["SUPERSET_DB_USER"], os.environ["SUPERSET_DB_PASSWORD"], "superset"),
    ]:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if not cur.fetchone():
            # DDL does not support parameterised PASSWORD, so we escape it.
            safe_pw = password.replace("'", "''")
            cur.execute(f'CREATE ROLE "{role}" WITH LOGIN PASSWORD \'{safe_pw}\'')
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{dbname}" OWNER "{role}"')

    cur.close()
    conn.close()
    return {"status": "ok"}
PYTHON

  depends_on = [terraform_data.build_lambda]
}

resource "aws_lambda_function" "db_bootstrap" {
  function_name = "${local.name_prefix}-db-bootstrap"
  role          = aws_iam_role.db_bootstrap.arn
  runtime       = "python3.12"
  handler       = "index.handler"
  timeout       = 30

  filename         = data.archive_file.db_bootstrap.output_path
  source_code_hash = data.archive_file.db_bootstrap.output_base64sha256

  vpc_config {
    subnet_ids      = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.ecs.id]
  }

  environment {
    variables = {
      DB_HOST              = aws_db_instance.main.address
      DB_PORT              = tostring(aws_db_instance.main.port)
      DB_USER              = var.db_username
      DB_PASSWORD          = random_password.db_master.result
      DB_NAME              = var.db_name
      AIRFLOW_DB_USER      = local.airflow_db_user
      AIRFLOW_DB_PASSWORD  = local.airflow_db_password
      SUPERSET_DB_USER     = local.superset_db_user
      SUPERSET_DB_PASSWORD = local.superset_db_password
    }
  }

  depends_on = [aws_iam_role_policy_attachment.db_bootstrap_vpc]
}

# Invoke the Lambda to create the airflow and superset databases
resource "terraform_data" "db_bootstrap" {
  depends_on = [aws_lambda_function.db_bootstrap, aws_db_instance.main]

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda invoke \
        --function-name "${aws_lambda_function.db_bootstrap.function_name}" \
        --region "${var.aws_region}" \
        --payload '{}' \
        --cli-binary-format raw-in-base64-out \
        /tmp/db_bootstrap_response.json && \
      cat /tmp/db_bootstrap_response.json
    EOT
  }
}
