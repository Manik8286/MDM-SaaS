#!/usr/bin/env bash
# upload_secrets.sh — Encode certificate/key files as base64 and upload
# them to AWS Secrets Manager.
#
# Run this after `terraform apply` to populate the placeholder secret values
# with your real APNs and MDM signing credentials.
#
# Usage:
#   APP_NAME=mdm-saas AWS_REGION=ap-south-1 ENVIRONMENT=production \
#     bash scripts/upload_secrets.sh
#
set -euo pipefail

APP_NAME="${APP_NAME:-mdm-saas}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"

PREFIX="${APP_NAME}-${ENVIRONMENT}"

CERT_DIR="certs/dev"

echo "=================================================="
echo "Uploading secrets to AWS Secrets Manager"
echo "  Prefix  : ${PREFIX}"
echo "  Region  : ${AWS_REGION}"
echo "  Cert dir: ${CERT_DIR}"
echo "=================================================="

# Helper function — encode a file as base64 and put it into a secret
put_secret() {
    local secret_name="$1"
    local file_path="$2"

    if [ ! -f "${file_path}" ]; then
        echo "[SKIP] File not found: ${file_path} (secret ${secret_name} not updated)"
        return 0
    fi

    echo "[...] Uploading ${file_path} → secret: ${secret_name}"

    # base64 encode (macOS uses -b 0 to disable line-wrapping; Linux uses -w 0)
    if base64 --version 2>&1 | grep -q GNU; then
        ENCODED=$(base64 -w 0 < "${file_path}")
    else
        ENCODED=$(base64 -b 0 < "${file_path}")
    fi

    aws secretsmanager put-secret-value \
        --region "${AWS_REGION}" \
        --secret-id "${secret_name}" \
        --secret-string "${ENCODED}"

    echo "[ OK] ${secret_name} updated."
}

# ---------------------------------------------------------------------------
# Upload each secret
# ---------------------------------------------------------------------------

echo ""
put_secret "${PREFIX}/apns-cert"       "${CERT_DIR}/apns.pem"
put_secret "${PREFIX}/apns-key"        "${CERT_DIR}/apns.key"
put_secret "${PREFIX}/mdm-signing-cert" "${CERT_DIR}/mdm_signing.pem"
put_secret "${PREFIX}/mdm-signing-key"  "${CERT_DIR}/mdm_signing.key"

echo ""
echo "=================================================="
echo "Done. All available secrets have been uploaded."
echo ""
echo "To verify, run:"
echo "  aws secretsmanager list-secrets --region ${AWS_REGION} \\"
echo "    --query \"SecretList[?starts_with(Name,'${PREFIX}')].Name\""
echo "=================================================="
