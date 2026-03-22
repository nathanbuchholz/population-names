output "ecs_cluster_name" {
  description = "ECS cluster name for service deployments"
  value       = aws_ecs_cluster.main.name
}

output "alb_dns_name" {
  description = "ALB DNS name - use this to access all services"
  value       = aws_lb.main.dns_name
}

output "api_url" {
  description = "Population Names API"
  value       = "http://${aws_lb.main.dns_name}"
}

output "airflow_url" {
  description = "Airflow UI"
  value       = "http://${aws_lb.main.dns_name}:8080"
}

output "superset_url" {
  description = "Superset UI"
  value       = "http://${aws_lb.main.dns_name}:8088"
}

output "ecr_api_repo" {
  description = "ECR repository URL for the API image"
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_airflow_repo" {
  description = "ECR repository URL for the Airflow image"
  value       = aws_ecr_repository.airflow.repository_url
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
}

output "s3_data_bucket" {
  description = "S3 bucket for pipeline data"
  value       = aws_s3_bucket.data.id
}

output "secrets_arn" {
  description = "Secrets Manager ARN"
  value       = aws_secretsmanager_secret.app.arn
}

# Used by post-deploy.sh for run-task calls
output "private_subnets" {
  description = "Private subnet IDs (comma-separated)"
  value       = join(",", aws_subnet.private[*].id)
}

output "ecs_security_group" {
  description = "ECS tasks security group ID"
  value       = aws_security_group.ecs.id
}
