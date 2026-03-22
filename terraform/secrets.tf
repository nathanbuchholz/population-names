# ---------------------------------------------------------------------------
# Random passwords (generated once, stored in state)
# ---------------------------------------------------------------------------

resource "random_password" "db_master" {
  length  = 32
  special = false
}

resource "random_password" "airflow_db" {
  length  = 32
  special = false
}

resource "random_password" "superset_db" {
  length  = 32
  special = false
}

resource "random_password" "api_key" {
  length  = 32
  special = false
}

resource "random_password" "airflow_fernet_key_bytes" {
  length  = 32
  special = false
}

resource "random_password" "airflow_secret_key" {
  length  = 32
  special = false
}

resource "random_password" "airflow_jwt_secret" {
  length  = 32
  special = false
}

resource "random_password" "airflow_admin_password" {
  length  = 24
  special = false
}

resource "random_password" "superset_secret_key" {
  length  = 42
  special = false
}

resource "random_password" "superset_admin_password" {
  length  = 24
  special = false
}

# ---------------------------------------------------------------------------
# Secrets Manager - single JSON secret with all credentials
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name_prefix}/app-secrets"
  description             = "Application secrets for ${var.project}"
  recovery_window_in_days = 0 # POC - immediate deletion on destroy
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    db_password             = random_password.db_master.result
    airflow_db_password     = random_password.airflow_db.result
    superset_db_password    = random_password.superset_db.result
    api_key                 = random_password.api_key.result
    airflow_fernet_key      = local.airflow_fernet_key
    airflow_secret_key      = random_password.airflow_secret_key.result
    airflow_jwt_secret      = random_password.airflow_jwt_secret.result
    airflow_admin_password  = random_password.airflow_admin_password.result
    airflow_admin_users     = local.airflow_admin_users
    superset_secret_key     = random_password.superset_secret_key.result
    superset_admin_password = random_password.superset_admin_password.result
  })
}
