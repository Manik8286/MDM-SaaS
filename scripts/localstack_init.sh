#!/bin/bash
set -e

echo "Initialising LocalStack resources..."

awslocal sqs create-queue --queue-name mdm-commands --region ap-south-1

awslocal secretsmanager create-secret \
  --name mdm/dev/apns-cert \
  --secret-string '{"placeholder": "replace-with-real-apns-cert"}' \
  --region ap-south-1 || true

awslocal secretsmanager create-secret \
  --name mdm/dev/apns-key \
  --secret-string '{"placeholder": "replace-with-real-apns-key"}' \
  --region ap-south-1 || true

echo "LocalStack init complete."
