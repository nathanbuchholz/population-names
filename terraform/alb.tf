# ---------------------------------------------------------------------------
# Application Load Balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = { Name = "${local.name_prefix}-alb" }
}

# ---------------------------------------------------------------------------
# Target groups
# ---------------------------------------------------------------------------

resource "aws_lb_target_group" "api" {
  name        = "${local.name_prefix}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }

  tags = { Name = "${local.name_prefix}-api-tg" }
}

resource "aws_lb_target_group" "airflow" {
  name        = "${local.name_prefix}-airflow"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/v2/monitor/health"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
  }

  tags = { Name = "${local.name_prefix}-airflow-tg" }
}

resource "aws_lb_target_group" "superset" {
  name        = "${local.name_prefix}-superset"
  port        = 8088
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
  }

  tags = { Name = "${local.name_prefix}-superset-tg" }
}

# ---------------------------------------------------------------------------
# Listeners - one per service on its own port (matches local Docker setup)
# ---------------------------------------------------------------------------

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_lb_listener" "airflow" {
  load_balancer_arn = aws_lb.main.arn
  port              = 8080
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.airflow.arn
  }
}

resource "aws_lb_listener" "superset" {
  load_balancer_arn = aws_lb.main.arn
  port              = 8088
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.superset.arn
  }
}
