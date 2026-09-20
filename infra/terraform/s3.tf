# ---------------------------------------------------------------------------
# Software package storage
#
# ECS Fargate tasks have no durable local disk — the /app/uploads volume the
# app writes to in Docker Compose disappears on every task restart/redeploy
# and isn't shared across tasks. Uploaded .pkg/.dmg installers need to live
# in S3 instead; app/api/routes/packages.py switches to S3 automatically
# when PACKAGES_S3_BUCKET is set (see ecs.tf).
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "packages" {
  # Bucket names are globally unique across all of AWS — suffix with the
  # account ID so this doesn't collide with another account's bucket.
  bucket = "${local.common_name}-packages-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${local.common_name}-packages"
  }
}

resource "aws_s3_bucket_public_access_block" "packages" {
  bucket = aws_s3_bucket.packages.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "packages" {
  bucket = aws_s3_bucket.packages.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "packages" {
  bucket = aws_s3_bucket.packages.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Installers only need to exist as long as an admin keeps them published —
# expire old versions after 90 days so accidental re-uploads don't
# accumulate storage cost forever.
resource "aws_s3_bucket_lifecycle_configuration" "packages" {
  bucket = aws_s3_bucket.packages.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
