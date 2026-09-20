from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "changeme"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 hours

    # Database
    database_url: str = "postgresql+asyncpg://mdm:mdm@localhost:5432/mdmdb"

    # AWS
    aws_region: str = "ap-south-1"
    sqs_command_queue_url: str = ""

    # APNs
    apns_cert_secret_arn: str = ""
    apns_key_secret_arn: str = ""
    apns_cert_path: str = "./certs/dev/apns.pem"
    apns_key_path: str = "./certs/dev/apns.key"
    apns_use_sandbox: bool = True

    # MDM profile signing
    mdm_signing_cert_path: str = "./certs/dev/mdm_signing.pem"
    mdm_signing_key_path: str = "./certs/dev/mdm_signing.key"

    # Software package storage. Empty = store on local disk (dev / docker
    # volume). Set to an S3 bucket name in production — Fargate tasks have no
    # durable local disk, so uploaded .pkg/.dmg files would vanish on restart.
    packages_s3_bucket: str = ""

    # mTLS CA cert
    mdm_ca_cert_path: str = "./certs/dev/ca.pem"

    # Public base URL of this server (used in enrollment profiles)
    mdm_server_url: str = "http://localhost:8000"

    # Public base URL for device mTLS endpoints (/mdm/apple/checkin, /connect).
    # In production this points at the ALB's mutual-TLS listener (a separate
    # port from mdm_server_url, since that listener requires every caller to
    # present a client cert — browsers/dashboard traffic must not go through it).
    # Falls back to mdm_server_url when unset (dev: no separate mTLS listener).
    mdm_device_url: str = ""

    # Dashboard public URL (used in OAuth2 redirect after SSO login)
    dashboard_url: str = "http://localhost:3000"

    # Entra ID OAuth2 (global / fallback — per-tenant values stored in DB)
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    # Redirect URI registered in Azure Portal — must use localhost for http to work
    # Defaults to localhost:8000 (browser-accessible), separate from mdm_server_url
    entra_redirect_uri: str = ""

    # Notifications — optional webhook URL (Slack/Teams/Discord incoming webhook)
    notification_webhook_url: str = ""

    # Transactional email (SMTP) — welcome emails, password reset, trial reminders.
    # In dev, docker-compose points this at a local Mailpit catcher (no real
    # delivery); see http://localhost:8025 to view sent mail.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = "no-reply@mdmconsole.local"
    smtp_from_name: str = "MDM Console"

    # Stripe billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_starter_price_id: str = ""   # Stripe Price ID for Starter plan
    stripe_pro_price_id: str = ""       # Stripe Price ID for Professional plan
    app_base_url: str = "http://localhost:3000"  # Dashboard URL for Stripe redirects

    # Platform admin — comma-separated emails allowed to see the cross-tenant
    # "Platform Admin" view (all customers + billing). These are ordinary
    # dashboard users; this just grants one extra page on top of their normal
    # tenant access. Empty = feature disabled for everyone.
    platform_admin_emails: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def mdm_device_base_url(self) -> str:
        return self.mdm_device_url or self.mdm_server_url

    @property
    def apns_host(self) -> str:
        return "api.sandbox.push.apple.com" if self.apns_use_sandbox else "api.push.apple.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
