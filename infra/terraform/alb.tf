# ---------------------------------------------------------------------------
# Security group - ALB (public-facing)
# ---------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${local.common_name}-alb-sg"
  description = "Allow HTTPS and HTTP inbound to ALB from anywhere"
  vpc_id      = aws_vpc.main.id

  ingress {
    description      = "HTTPS from internet (IPv4)"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTP from internet (IPv4) - redirected to HTTPS"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.common_name}-alb-sg"
  }
}

# ---------------------------------------------------------------------------
# Security group - ECS tasks (private)
# ---------------------------------------------------------------------------

resource "aws_security_group" "ecs" {
  name        = "${local.common_name}-ecs-sg"
  description = "Allow inbound port 8000 from ALB only; allow all outbound"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "FastAPI port from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "Allow all outbound (SQS, APNs, Secrets Manager, RDS)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.common_name}-ecs-sg"
  }
}

# ---------------------------------------------------------------------------
# Application Load Balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "main" {
  name               = "${local.common_name}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = [aws_subnet.public_a.id, aws_subnet.public_b.id]
  security_groups    = [aws_security_group.alb.id]

  tags = {
    Name = "${local.common_name}-alb"
  }
}

# ---------------------------------------------------------------------------
# Target group - FastAPI on port 8000
# ---------------------------------------------------------------------------

resource "aws_lb_target_group" "api" {
  name        = "${local.common_name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/healthz"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 10
    matcher             = "200"
  }

  tags = {
    Name = "${local.common_name}-api-tg"
  }
}

# ---------------------------------------------------------------------------
# HTTPS listener (port 443)
# ---------------------------------------------------------------------------

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  tags = {
    Name = "${local.common_name}-https-listener"
  }
}

# ---------------------------------------------------------------------------
# HTTP listener (port 80) - redirect to HTTPS
# ---------------------------------------------------------------------------

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      protocol    = "HTTPS"
      port        = "443"
      status_code = "HTTP_301"
    }
  }

  tags = {
    Name = "${local.common_name}-http-redirect-listener"
  }
}
