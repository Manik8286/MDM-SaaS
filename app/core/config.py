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

    # mTLS CA cert
    mdm_ca_cert_path: str = "./certs/dev/ca.pem"

    # Public base URL of this server (used in enrollment profiles)
    mdm_server_url: str = "http://localhost:8000"

    # Dashboard public URL (used in OAuth2 redirect after SSO login)
    dashboard_url: str = "http://localhost:3000"

    # Entra ID OAuth2 (global / fallback — per-tenant values stored in DB)
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    # Redirect URI registered in Azure Portal — must use localhost for http to work
    # Defaults to localhost:8000 (browser-accessible), separate from mdm_server_url
    entra_redirect_uri: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def apns_host(self) -> str:
        return "api.sandbox.push.apple.com" if self.apns_use_sandbox else "api.push.apple.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
