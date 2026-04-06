# ---------------------------------------------------------------------------
# CloudWatch log group
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.common_name}"
  retention_in_days = 30

  tags = {
    Name = "/ecs/${local.common_name}"
  }
}

# ---------------------------------------------------------------------------
# ECS cluster
# ---------------------------------------------------------------------------

resource "aws_ecs_cluster" "main" {
  name = local.common_name

  tags = {
    Name = local.common_name
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ---------------------------------------------------------------------------
# API task definition
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.common_name}-api"
  cpu                      = var.api_task_cpu
  memory                   = var.api_task_memory
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "ENVIRONMENT", value = "production" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "SQS_COMMAND_QUEUE_URL", value = aws_sqs_queue.commands.url },
        { name = "MDM_SERVER_URL", value = "https://${var.domain_name}" },
        { name = "APNS_USE_SANDBOX", value = tostring(var.apns_use_sandbox) },
        { name = "MIGRATE", value = "1" },
        { name = "DB_HOST", value = aws_db_instance.main.address },
        { name = "DB_PORT", value = "5432" },
        { name = "DB_NAME", value = "mdmdb" },
        { name = "DB_USER", value = "mdm" },
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.jwt_secret.arn
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = aws_secretsmanager_secret.db_password.arn
        },
        {
          name      = "APNS_CERT_B64"
          valueFrom = aws_secretsmanager_secret.apns_cert.arn
        },
        {
          name      = "APNS_KEY_B64"
          valueFrom = aws_secretsmanager_secret.apns_key.arn
        },
        {
          name      = "MDM_SIGNING_CERT_B64"
          valueFrom = aws_secretsmanager_secret.mdm_signing_cert.arn
        },
        {
          name      = "MDM_SIGNING_KEY_B64"
          valueFrom = aws_secretsmanager_secret.mdm_signing_key.arn
        },
        {
          name      = "DEVICE_IDENTITY_P12_B64"
          valueFrom = aws_secretsmanager_secret.device_identity_p12.arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/healthz || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
      }

      essential = true
    }
  ])

  tags = {
    Name = "${local.common_name}-api"
  }
}

# ---------------------------------------------------------------------------
# Worker task definition (SQS consumer)
# ---------------------------------------------------------------------------

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.common_name}-worker"
  cpu                      = var.worker_task_cpu
  memory                   = var.worker_task_memory
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name    = "worker"
      image   = "${aws_ecr_repository.app.repository_url}:latest"
      command = ["python", "-m", "app.services.command_queue"]

      environment = [
        { name = "ENVIRONMENT", value = "production" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "SQS_COMMAND_QUEUE_URL", value = aws_sqs_queue.commands.url },
        { name = "MDM_SERVER_URL", value = "https://${var.domain_name}" },
        { name = "APNS_USE_SANDBOX", value = tostring(var.apns_use_sandbox) },
        { name = "MIGRATE", value = "0" },
        { name = "DB_HOST", value = aws_db_instance.main.address },
        { name = "DB_PORT", value = "5432" },
        { name = "DB_NAME", value = "mdmdb" },
        { name = "DB_USER", value = "mdm" },
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.jwt_secret.arn
        },
        {
          name      = "DB_PASSWORD"
          valueFrom = aws_secretsmanager_secret.db_password.arn
        },
        {
          name      = "APNS_CERT_B64"
          valueFrom = aws_secretsmanager_secret.apns_cert.arn
        },
        {
          name      = "APNS_KEY_B64"
          valueFrom = aws_secretsmanager_secret.apns_key.arn
        },
        {
          name      = "MDM_SIGNING_CERT_B64"
          valueFrom = aws_secretsmanager_secret.mdm_signing_cert.arn
        },
        {
          name      = "MDM_SIGNING_KEY_B64"
          valueFrom = aws_secretsmanager_secret.mdm_signing_key.arn
        },
        {
          name      = "DEVICE_IDENTITY_P12_B64"
          valueFrom = aws_secretsmanager_secret.device_identity_p12.arn
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }

      essential = true
    }
  ])

  tags = {
    Name = "${local.common_name}-worker"
  }
}

# ---------------------------------------------------------------------------
# API ECS service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "api" {
  name            = "${local.common_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  enable_execute_command = true

  depends_on = [
    aws_lb_listener.https,
    aws_lb_listener.http_redirect,
  ]

  tags = {
    Name = "${local.common_name}-api"
  }
}

# ---------------------------------------------------------------------------
# Worker ECS service
# ---------------------------------------------------------------------------

resource "aws_ecs_service" "worker" {
  name            = "${local.common_name}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [aws_subnet.private_a.id, aws_subnet.private_b.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 200

  enable_execute_command = true

  tags = {
    Name = "${local.common_name}-worker"
  }
}
