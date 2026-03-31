#!/usr/bin/env bash
# tf_bootstrap.sh — Create S3 bucket and DynamoDB table for Terraform remote state.
# Run this ONCE before the first `terraform init` for a new environment.
#
# Usage:
#   APP_NAME=mdm-saas AWS_REGION=ap-south-1 bash scripts/tf_bootstrap.sh
#
set -euo pipefail

APP_NAME="${APP_NAME:-mdm-saas}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

BUCKET_NAME="${APP_NAME}-terraform-state"
TABLE_NAME="${APP_NAME}-terraform-locks"

echo "=================================================="
echo "Terraform state bootstrap"
echo "  App name  : ${APP_NAME}"
echo "  Region    : ${AWS_REGION}"
echo "  S3 bucket : ${BUCKET_NAME}"
echo "  DynamoDB  : ${TABLE_NAME}"
echo "=================================================="

# ---------------------------------------------------------------------------
# S3 bucket for Terraform state
# ---------------------------------------------------------------------------

echo ""
echo "[1/5] Creating S3 bucket: ${BUCKET_NAME}"

# ap-south-1 (and all non-us-east-1 regions) require LocationConstraint
if [ "${AWS_REGION}" = "us-east-1" ]; then
    aws s3api create-bucket \
        --bucket "${BUCKET_NAME}" \
        --region "${AWS_REGION}"
else
    aws s3api create-bucket \
        --bucket "${BUCKET_NAME}" \
        --region "${AWS_REGION}" \
        --create-bucket-configuration LocationConstraint="${AWS_REGION}"
fi

echo "[2/5] Enabling versioning on s3://${BUCKET_NAME}"
aws s3api put-bucket-versioning \
    --bucket "${BUCKET_NAME}" \
    --versioning-configuration Status=Enabled

echo "[3/5] Enabling server-side encryption (AES256)"
aws s3api put-bucket-encryption \
    --bucket "${BUCKET_NAME}" \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'

echo "[4/5] Blocking all public access"
aws s3api put-public-access-block \
    --bucket "${BUCKET_NAME}" \
    --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# ---------------------------------------------------------------------------
# DynamoDB table for state locking
# ---------------------------------------------------------------------------

echo "[5/5] Creating DynamoDB table: ${TABLE_NAME}"
aws dynamodb create-table \
    --table-name "${TABLE_NAME}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${AWS_REGION}"

echo ""
echo "=================================================="
echo "Bootstrap complete."
echo ""
echo "Next steps:"
echo "  1. cd infra/terraform"
echo "  2. terraform init"
echo "  3. Copy terraform.tfvars.example to terraform.tfvars and fill in values"
echo "  4. terraform plan"
echo "  5. terraform apply"
echo "=================================================="
