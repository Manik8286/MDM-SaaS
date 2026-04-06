# ---------------------------------------------------------------------------
# Random value for the JWT signing key
# ---------------------------------------------------------------------------

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

# ---------------------------------------------------------------------------
# 1. JWT signing secret
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "jwt_secret" {
  name        = "${local.common_name}/jwt-secret"
  description = "JWT signing key"

  tags = {
    Name = "${local.common_name}/jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

# ---------------------------------------------------------------------------
# 2. Database password (same random_password resource as in rds.tf)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "db_password" {
  name        = "${local.common_name}/db-password"
  description = "RDS master user password"

  tags = {
    Name = "${local.common_name}/db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db_password.result
}

# ---------------------------------------------------------------------------
# 3. APNs push certificate (base64-encoded PEM)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "apns_cert" {
  name        = "${local.common_name}/apns-cert"
  description = "Base64-encoded APNs push certificate PEM"

  tags = {
    Name = "${local.common_name}/apns-cert"
  }
}

resource "aws_secretsmanager_secret_version" "apns_cert" {
  secret_id     = aws_secretsmanager_secret.apns_cert.id
  secret_string = "REPLACE_WITH_BASE64_APNS_CERT"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# 4. APNs private key (base64-encoded PEM)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "apns_key" {
  name        = "${local.common_name}/apns-key"
  description = "Base64-encoded APNs private key PEM"

  tags = {
    Name = "${local.common_name}/apns-key"
  }
}

resource "aws_secretsmanager_secret_version" "apns_key" {
  secret_id     = aws_secretsmanager_secret.apns_key.id
  secret_string = "REPLACE_WITH_BASE64_APNS_KEY"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# 5. MDM profile signing certificate (base64-encoded PEM)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "mdm_signing_cert" {
  name        = "${local.common_name}/mdm-signing-cert"
  description = "Base64-encoded MDM profile signing certificate PEM"

  tags = {
    Name = "${local.common_name}/mdm-signing-cert"
  }
}

resource "aws_secretsmanager_secret_version" "mdm_signing_cert" {
  secret_id     = aws_secretsmanager_secret.mdm_signing_cert.id
  secret_string = "REPLACE_WITH_BASE64_MDM_SIGNING_CERT"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# 6. MDM profile signing key (base64-encoded PEM)
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "mdm_signing_key" {
  name        = "${local.common_name}/mdm-signing-key"
  description = "Base64-encoded MDM profile signing private key PEM"

  tags = {
    Name = "${local.common_name}/mdm-signing-key"
  }
}

resource "aws_secretsmanager_secret_version" "mdm_signing_key" {
  secret_id     = aws_secretsmanager_secret.mdm_signing_key.id
  secret_string = "REPLACE_WITH_BASE64_MDM_SIGNING_KEY"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "device_identity_p12" {
  name        = "${local.common_name}/device-identity-p12"
  description = "Base64-encoded PKCS12 device identity certificate for enrollment profiles"

  tags = {
    Name = "${local.common_name}/device-identity-p12"
  }
}

resource "aws_secretsmanager_secret_version" "device_identity_p12" {
  secret_id     = aws_secretsmanager_secret.device_identity_p12.id
  secret_string = "REPLACE_WITH_BASE64_DEVICE_IDENTITY_P12"

  lifecycle {
    ignore_changes = [secret_string]
  }
}
