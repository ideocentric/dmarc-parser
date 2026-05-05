from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "development"
    secret_key: str  # required — set SECRET_KEY in .env; no default to prevent insecure deployments
    log_level: str = "INFO"

    # Database — single URL for all tenants
    # SQLite (default):      sqlite:///data/dmarc.db
    # PostgreSQL:            postgresql+psycopg2://user:pass@host:5432/dmarc
    database_url: str = "sqlite:///data/dmarc.db"

    # Report storage
    reports_base_dir: Path = Path("data/reports")
    archive_retention_days: int = 7

    # Credential encryption (Fernet key — generate once, store in .env)
    encryption_key: str  # required — set ENCRYPTION_KEY in .env; generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # GeoIP
    geoip_db_path: Path = Path("data/GeoLite2-City.mmdb")

    # ClamAV antivirus scanning (optional — disabled by default)
    clamav_enabled: bool = False       # set CLAMAV_ENABLED=true to enable
    clamav_host: str = "localhost"     # clamd TCP host
    clamav_port: int = 3310            # clamd TCP port
    # When True: unreachable clamd logs a warning and allows the file through (availability).
    # When False (default): unreachable clamd logs an error and rejects the file (security).
    # Use False in compliance/regulated environments.
    clamav_fail_open: bool = False

    # MFA enforcement
    mfa_required: bool = False  # when True, all users must enrol before accessing the platform

    # Azure SSO
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_redirect_uri: str = "http://localhost:5173/auth/callback"
    azure_auto_provision: bool = False  # when False, unknown SSO users are rejected (403)

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def incoming_dir(self) -> Path:
        return self.reports_base_dir / "incoming"

    @property
    def archive_dir(self) -> Path:
        return self.reports_base_dir / "archive"

    def client_incoming_dir(self, client_slug: str) -> Path:
        result = (self.incoming_dir / client_slug).resolve()
        if not str(result).startswith(str(self.incoming_dir.resolve())):
            raise ValueError(f"client_slug {client_slug!r} escapes the base reports directory")
        return result

    def client_archive_dir(self, client_slug: str) -> Path:
        result = (self.archive_dir / client_slug).resolve()
        if not str(result).startswith(str(self.archive_dir.resolve())):
            raise ValueError(f"client_slug {client_slug!r} escapes the base reports directory")
        return result


settings = Settings()