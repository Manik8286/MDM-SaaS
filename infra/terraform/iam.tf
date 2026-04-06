# ---------------------------------------------------------------------------
# Shared trust-policy data source for ECS tasks
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    sid     = "AllowECSTasksToAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------------------------------------------------------------------------
# ECS Task Execution Role
# Used by the ECS agent to pull images, write logs and fetch secrets at
# container startup time.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.common_name}-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = {
    Name = "${local.common_name}-ecs-task-execution"
  }
}

# Attach the AWS-managed execution policy (ECR pull + CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Inline policy: read all 6 secrets at task startup
data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.jwt_secret.arn,
      aws_secretsmanager_secret.db_password.arn,
      aws_secretsmanager_secret.apns_cert.arn,
      aws_secretsmanager_secret.apns_key.arn,
      aws_secretsmanager_secret.mdm_signing_cert.arn,
      aws_secretsmanager_secret.mdm_signing_key.arn,
      aws_secretsmanager_secret.device_identity_p12.arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "read-secrets"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_task_execution_secrets.json
}

# ---------------------------------------------------------------------------
# ECS Task Role
# Assumed by the running application container - grants access to AWS
# services the app calls at runtime (SQS, Secrets Manager, CloudWatch Logs).
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ecs_task" {
  name               = "${local.common_name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = {
    Name = "${local.common_name}-ecs-task"
  }
}

data "aws_iam_policy_document" "ecs_task_permissions" {
  # SQS - command queue and DLQ
  statement {
    sid    = "SQSAccess"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [
      aws_sqs_queue.commands.arn,
      aws_sqs_queue.commands_dlq.arn,
    ]
  }

  # Secrets Manager - runtime secret reads (e.g. key rotation without restart)
  statement {
    sid    = "ReadSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.jwt_secret.arn,
      aws_secretsmanager_secret.db_password.arn,
      aws_secretsmanager_secret.apns_cert.arn,
      aws_secretsmanager_secret.apns_key.arn,
      aws_secretsmanager_secret.mdm_signing_cert.arn,
      aws_secretsmanager_secret.mdm_signing_key.arn,
      aws_secretsmanager_secret.device_identity_p12.arn,
    ]
  }

  # CloudWatch Logs
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:*:*"]
  }
}

resource "aws_iam_role_policy" "ecs_task_permissions" {
  name   = "task-permissions"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_permissions.json
}
