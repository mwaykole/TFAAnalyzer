"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReportPortalConfig(BaseSettings):
    """ReportPortal connection configuration."""

    url: str = Field(..., description="ReportPortal server URL")
    token: str | None = Field(default=None, description="ReportPortal API token")
    username: str | None = Field(default=None, description="ReportPortal username")
    password: str | None = Field(default=None, description="ReportPortal password")
    project: str = Field(..., description="ReportPortal project name")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")

    @field_validator("url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    provider: Literal["anthropic"] = Field(
        default="anthropic", description="LLM provider"
    )
    model: str = Field(
        default="claude-sonnet-4-20250514", description="Model identifier"
    )
    max_tokens: int = Field(default=4096, description="Maximum response tokens")
    temperature: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Response temperature"
    )


class AnalysisConfig(BaseSettings):
    """Analysis behavior configuration."""

    max_concurrent_requests: int = Field(
        default=5, ge=1, le=20, description="Max concurrent API requests"
    )
    chunk_size: int = Field(
        default=150000, ge=1000, description="Max characters per log chunk"
    )
    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Min confidence threshold"
    )
    include_recommendation: bool = Field(
        default=True, description="Include fix recommendations"
    )


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Log level"
    )
    format: Literal["json", "console"] = Field(
        default="json", description="Log format"
    )


class RetryConfig(BaseSettings):
    """Retry behavior configuration."""

    max_attempts: int = Field(default=3, ge=1, le=10, description="Max retry attempts")
    base_delay: float = Field(default=1.0, ge=0.1, description="Base delay in seconds")
    max_delay: float = Field(default=30.0, ge=1.0, description="Max delay in seconds")
    exponential_base: float = Field(default=2.0, ge=1.1, description="Backoff base")


class TestRepoConfig(BaseSettings):
    """Test repository configuration for fetching test source code."""

    enabled: bool = Field(default=False, description="Enable test code fetching")
    repo: str = Field(default="", description="GitHub repo (owner/repo format)")
    branch: str = Field(default="main", description="Branch to fetch from")
    test_dir: str = Field(default="tests", description="Directory containing tests")
    local_path: str | None = Field(default=None, description="Local path to test repo (optional)")
    github_token: str | None = Field(default=None, description="GitHub token for private repos")
    cache_dir: str = Field(default=".code_cache", description="Directory to cache fetched code")


class NotificationConfig(BaseSettings):
    """Notification configuration for Slack/Teams alerts."""

    enabled: bool = Field(default=False, description="Enable notifications")
    slack_webhook: str | None = Field(default=None, description="Slack incoming webhook URL")
    teams_webhook: str | None = Field(default=None, description="Teams incoming webhook URL")
    notify_on_bugs: bool = Field(default=True, description="Notify when product bugs found")
    notify_on_completion: bool = Field(default=True, description="Notify when analysis completes")
    min_failures_to_notify: int = Field(default=1, ge=0, description="Min failures to trigger notification")


class VerificationConfig(BaseSettings):
    """Test verification configuration."""

    timeout_per_test: int = Field(default=120, ge=30, le=600, description="Timeout per test in seconds")
    max_parallel: int = Field(default=2, ge=1, le=5, description="Max parallel test runs")
    skip_on_low_confidence: bool = Field(default=True, description="Skip verification if confidence > 80%")
    confidence_threshold: float = Field(default=0.8, description="Skip verification above this confidence")


class CacheConfig(BaseSettings):
    """Caching configuration for analysis results."""

    enabled: bool = Field(default=True, description="Enable result caching")
    backend: Literal["memory", "redis"] = Field(default="memory", description="Cache backend")
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    ttl_seconds: int = Field(default=86400, ge=60, description="Cache TTL in seconds (24h default)")
    prefix: str = Field(default="tfa:", description="Cache key prefix")


class ClusterConfig(BaseSettings):
    """Configuration for a single cluster/environment."""

    name: str = Field(..., description="Cluster display name")
    rp_project: str = Field(..., description="ReportPortal project name")
    rp_url: str | None = Field(default=None, description="Override RP URL for this cluster")
    rp_username: str | None = Field(default=None, description="Override username")
    rp_password: str | None = Field(default=None, description="Override password")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    reportportal: ReportPortalConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    test_repo: TestRepoConfig = Field(default_factory=TestRepoConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    clusters: list[dict] = Field(default_factory=list, description="Multi-cluster configurations")

    # Direct environment variable overrides
    rp_url: str | None = Field(default=None, alias="RP_URL")
    rp_token: str | None = Field(default=None, alias="RP_TOKEN")
    rp_username: str | None = Field(default=None, alias="RP_USERNAME")
    rp_password: str | None = Field(default=None, alias="RP_PASSWORD")
    rp_project: str | None = Field(default=None, alias="RP_PROJECT")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    slack_webhook_url: str | None = Field(default=None, alias="SLACK_WEBHOOK_URL")
    teams_webhook_url: str | None = Field(default=None, alias="TEAMS_WEBHOOK_URL")

    def get_rp_url(self) -> str:
        url = self.rp_url or self.reportportal.url
        if not url or url.startswith("${"):
            raise ValueError("RP_URL environment variable is required")
        return url

    def get_rp_token(self) -> str | None:
        token = self.rp_token or self.reportportal.token
        if token and token.startswith("${"):
            return None
        return token or None

    def get_rp_username(self) -> str | None:
        username = self.rp_username or self.reportportal.username
        if username and username.startswith("${"):
            return None
        return username or None

    def get_rp_password(self) -> str | None:
        password = self.rp_password or self.reportportal.password
        if password and password.startswith("${"):
            return None
        return password or None

    def get_rp_project(self) -> str:
        project = self.rp_project or self.reportportal.project
        if not project or project.startswith("${"):
            raise ValueError("RP_PROJECT environment variable is required")
        return project

    def get_anthropic_key(self) -> str:
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        return self.anthropic_api_key

    def get_rp_auth(self) -> tuple[str | None, str | None, str | None]:
        """Get ReportPortal authentication credentials.
        
        Returns:
            Tuple of (token, username, password)
        """
        return (self.get_rp_token(), self.get_rp_username(), self.get_rp_password())
    
    def get_github_token(self) -> str | None:
        """Get GitHub token for private repos."""
        token = self.github_token or self.test_repo.github_token
        if token and token.startswith("${"):
            return None
        return token
    
    def get_slack_webhook(self) -> str | None:
        """Get Slack webhook URL."""
        webhook = self.slack_webhook_url or self.notifications.slack_webhook
        if webhook and webhook.startswith("${"):
            return None
        return webhook
    
    def get_teams_webhook(self) -> str | None:
        """Get Teams webhook URL."""
        webhook = self.teams_webhook_url or self.notifications.teams_webhook
        if webhook and webhook.startswith("${"):
            return None
        return webhook
    
    def is_notifications_enabled(self) -> bool:
        """Check if notifications are enabled and configured."""
        return self.notifications.enabled and (
            bool(self.get_slack_webhook()) or bool(self.get_teams_webhook())
        )
    
    def is_code_fetcher_enabled(self) -> bool:
        """Check if code fetcher is enabled and configured."""
        return self.test_repo.enabled and (
            bool(self.test_repo.repo) or bool(self.test_repo.local_path)
        )


def load_yaml_config(config_path: Path) -> dict:
    """Load configuration from YAML file with environment variable substitution."""
    if not config_path.exists():
        return {}

    with open(config_path) as f:
        content = f.read()

    import os
    import re

    def replace_env_var(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    content = re.sub(r"\$\{(\w+)\}", replace_env_var, content)
    return yaml.safe_load(content) or {}


def create_settings(config_path: Path | None = None) -> Settings:
    """Create settings from config file and environment variables."""
    import os
    from dotenv import load_dotenv

    load_dotenv(override=True)

    config_data: dict = {}

    if config_path and config_path.exists():
        config_data = load_yaml_config(config_path)
    else:
        default_path = Path("config.yaml")
        if default_path.exists():
            config_data = load_yaml_config(default_path)

    if "reportportal" not in config_data:
        config_data["reportportal"] = {
            "url": os.environ.get("RP_URL", ""),
            "token": os.environ.get("RP_TOKEN", ""),
            "username": os.environ.get("RP_USERNAME", ""),
            "password": os.environ.get("RP_PASSWORD", ""),
            "project": os.environ.get("RP_PROJECT", ""),
        }

    return Settings(**config_data)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return create_settings()

