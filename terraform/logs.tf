# ---------------------------------------------------------------------------
# CloudWatch log groups
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name_prefix}/api"
  retention_in_days = 7 # POC

  tags = { Name = "${local.name_prefix}-api-logs" }
}

resource "aws_cloudwatch_log_group" "airflow_webserver" {
  name              = "/ecs/${local.name_prefix}/airflow-webserver"
  retention_in_days = 7

  tags = { Name = "${local.name_prefix}-airflow-webserver-logs" }
}

resource "aws_cloudwatch_log_group" "airflow_scheduler" {
  name              = "/ecs/${local.name_prefix}/airflow-scheduler"
  retention_in_days = 7

  tags = { Name = "${local.name_prefix}-airflow-scheduler-logs" }
}

resource "aws_cloudwatch_log_group" "superset" {
  name              = "/ecs/${local.name_prefix}/superset"
  retention_in_days = 7

  tags = { Name = "${local.name_prefix}-superset-logs" }
}
