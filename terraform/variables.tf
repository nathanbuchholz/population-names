variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

variable "project" {
  description = "Project name used for resource naming"
  type        = string
  default     = "api-demo"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "poc"
}

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones (2 for POC)"
  type        = number
  default     = 2
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class (db.t3.micro is Free Tier eligible)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Primary database name"
  type        = string
  default     = "population_names"
}

variable "db_username" {
  description = "Master database username"
  type        = string
  default     = "pipeline"
}

# ---------------------------------------------------------------------------
# ECS
# ---------------------------------------------------------------------------

variable "api_cpu" {
  description = "CPU units for the API task (1024 = 1 vCPU)"
  type        = number
  default     = 256
}

variable "api_memory" {
  description = "Memory (MiB) for the API task"
  type        = number
  default     = 512
}

variable "api_desired_count" {
  description = "Number of API tasks"
  type        = number
  default     = 1
}

variable "airflow_cpu" {
  description = "CPU units for Airflow tasks"
  type        = number
  default     = 512
}

variable "airflow_memory" {
  description = "Memory (MiB) for Airflow tasks"
  type        = number
  default     = 1024
}

variable "superset_cpu" {
  description = "CPU units for Superset"
  type        = number
  default     = 512
}

variable "superset_memory" {
  description = "Memory (MiB) for Superset"
  type        = number
  default     = 1024
}

# ---------------------------------------------------------------------------
# Container image tags (set after first push to ECR)
# ---------------------------------------------------------------------------

variable "api_image_tag" {
  description = "Tag for the API container image"
  type        = string
  default     = "latest"
}

variable "airflow_image_tag" {
  description = "Tag for the Airflow container image"
  type        = string
  default     = "latest"
}

variable "superset_image" {
  description = "Full image reference for Superset (public image, not built from this repo)"
  type        = string
  default     = "apache/superset:6.0.0"
}
