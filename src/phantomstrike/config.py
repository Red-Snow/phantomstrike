"""
PhantomStrike Configuration — single source of truth for all settings.

Reads from environment variables and .env file with sensible defaults.
"""

import os
import secrets
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServerConfig:
    """API server settings."""
    host: str = "127.0.0.1"
    port: int = 8443
    workers: int = 1
    reload: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class AuthConfig:
    """Authentication & authorization settings."""
    enabled: bool = True
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours
    api_keys: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.secret_key:
            self.secret_key = os.getenv("PHANTOMSTRIKE_SECRET_KEY", secrets.token_hex(32))


@dataclass
class ExecutionConfig:
    """Tool execution settings."""
    max_concurrent_jobs: int = 5
    default_timeout: int = 600  # 10 minutes
    use_docker_sandbox: bool = False
    docker_image: str = "phantomstrike/runner:latest"
    workspace_dir: str = "/tmp/phantomstrike"
    cache_enabled: bool = True
    cache_ttl: int = 3600  # 1 hour


@dataclass
class DatabaseConfig:
    """Storage settings."""
    url: str = ""
    echo: bool = False

    def __post_init__(self):
        if not self.url:
            db_dir = Path.home() / ".phantomstrike"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.url = f"sqlite+aiosqlite:///{db_dir / 'phantomstrike.db'}"


@dataclass
class LoggingConfig:
    """Logging settings."""
    level: str = "INFO"
    file: Optional[str] = None
    json_format: bool = False


@dataclass
class PhantomStrikeConfig:
    """Root configuration container."""
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_env(cls) -> "PhantomStrikeConfig":
        """Build config from environment variables."""
        config = cls()

        # Server
        config.server.host = os.getenv("PHANTOMSTRIKE_HOST", config.server.host)
        config.server.port = int(os.getenv("PHANTOMSTRIKE_PORT", str(config.server.port)))
        config.server.reload = os.getenv("PHANTOMSTRIKE_RELOAD", "").lower() == "true"

        # Auth
        config.auth.enabled = os.getenv("PHANTOMSTRIKE_AUTH_ENABLED", "true").lower() == "true"
        if api_keys_env := os.getenv("PHANTOMSTRIKE_API_KEYS"):
            config.auth.api_keys = [k.strip() for k in api_keys_env.split(",") if k.strip()]

        # Execution
        config.execution.max_concurrent_jobs = int(
            os.getenv("PHANTOMSTRIKE_MAX_JOBS", str(config.execution.max_concurrent_jobs))
        )
        config.execution.default_timeout = int(
            os.getenv("PHANTOMSTRIKE_TIMEOUT", str(config.execution.default_timeout))
        )
        config.execution.use_docker_sandbox = (
            os.getenv("PHANTOMSTRIKE_DOCKER_SANDBOX", "").lower() == "true"
        )
        config.execution.workspace_dir = os.getenv(
            "PHANTOMSTRIKE_WORKSPACE", config.execution.workspace_dir
        )

        # Database
        if db_url := os.getenv("PHANTOMSTRIKE_DB_URL"):
            config.database.url = db_url

        # Logging
        config.logging.level = os.getenv("PHANTOMSTRIKE_LOG_LEVEL", config.logging.level)
        config.logging.file = os.getenv("PHANTOMSTRIKE_LOG_FILE")

        return config


# Global singleton — import this everywhere
settings = PhantomStrikeConfig.from_env()
