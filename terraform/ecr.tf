# ---------------------------------------------------------------------------
# ECR repositories
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "api" {
  name                 = "${local.name_prefix}/api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # POC

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${local.name_prefix}-api" }
}

resource "aws_ecr_repository" "airflow" {
  name                 = "${local.name_prefix}/airflow"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # POC

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${local.name_prefix}-airflow" }
}

# Lifecycle policy - keep only last 5 images (POC cost control)
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecr_lifecycle_policy" "airflow" {
  repository = aws_ecr_repository.airflow.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
