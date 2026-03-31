# ---------------------------------------------------------------------------
# Dead-letter queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "commands_dlq" {
  name                      = "${local.common_name}-commands-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "${local.common_name}-commands-dlq"
  }
}

# ---------------------------------------------------------------------------
# Main command queue
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "commands" {
  name                       = "${local.common_name}-commands"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400 # 24 hours
  receive_wait_time_seconds  = 20    # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.commands_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${local.common_name}-commands"
  }
}

# ---------------------------------------------------------------------------
# Queue policy - allow ECS task role to send and receive messages
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "sqs_commands_policy" {
  statement {
    sid    = "AllowECSTaskAccess"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.ecs_task.arn]
    }

    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]

    resources = [aws_sqs_queue.commands.arn]
  }
}

resource "aws_sqs_queue_policy" "commands" {
  queue_url = aws_sqs_queue.commands.id
  policy    = data.aws_iam_policy_document.sqs_commands_policy.json
}
