data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  azs         = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # Subnet CIDR calculation: /24 blocks within the VPC
  public_subnets  = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 100)]

  # Container image URIs
  api_image     = "${aws_ecr_repository.api.repository_url}:${var.api_image_tag}"
  airflow_image = "${aws_ecr_repository.airflow.repository_url}:${var.airflow_image_tag}"

  # Database connection strings for containers
  db_host     = aws_db_instance.main.address
  db_port     = aws_db_instance.main.port
  db_password = random_password.db_master.result

  pipeline_db_url       = "postgresql://${var.db_username}:${local.db_password}@${local.db_host}:${local.db_port}/${var.db_name}"
  pipeline_db_url_async = "postgresql+asyncpg://${var.db_username}:${local.db_password}@${local.db_host}:${local.db_port}/${var.db_name}"
  airflow_db_url        = "postgresql+psycopg2://${local.airflow_db_user}:${local.airflow_db_password}@${local.db_host}:${local.db_port}/airflow"
  superset_db_url       = "postgresql+psycopg2://${local.superset_db_user}:${local.superset_db_password}@${local.db_host}:${local.db_port}/superset"

  airflow_db_user      = "airflow"
  airflow_db_password  = random_password.airflow_db.result
  superset_db_user     = "superset"
  superset_db_password = random_password.superset_db.result

  # Airflow Fernet key must be base64-encoded 32 bytes.
  # We take the first 32 bytes of the random password and base64-encode them.
  airflow_fernet_key = base64encode(substr(random_password.airflow_fernet_key_bytes.result, 0, 32))

  # Airflow simple auth manager users format: "username:password"
  airflow_admin_users = "admin:${random_password.airflow_admin_password.result}"
}
