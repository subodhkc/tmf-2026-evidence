"""
LogSense Settings Module
Centralized configuration management using Pydantic Settings.
"""

import tempfile
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Deployment environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMMode(str, Enum):
    """LLM availability mode."""
    DISABLED = "disabled"
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment-based LLM strategy:
    - development: Local LLM (Phi-2) enabled
    - staging: Cloud AI (OpenAI) enabled
    - production: All LLM disabled (deterministic only)
    """

    # ============================================================
    # ENVIRONMENT
    # ============================================================

    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Debug mode")

    # ============================================================
    # API CONFIGURATION
    # ============================================================

    api_host: str = Field(default="127.0.0.1", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")

    # ============================================================
    # DATABASE
    # ============================================================

    supabase_url: str | None = Field(default=None, description="Supabase URL")
    supabase_key: str | None = Field(default=None, description="Supabase anon key")
    supabase_service_key: str | None = Field(default=None, description="Supabase service key")

    # ============================================================
    # REDIS / CELERY
    # ============================================================

    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    celery_broker_url: str | None = Field(default=None, description="Celery broker URL")
    celery_result_backend: str | None = Field(default=None, description="Celery result backend")

    # ============================================================
    # FILE HANDLING
    # ============================================================

    max_file_size_mb: int = Field(default=25, description="Max file size in MB")
    max_files_per_analysis: int = Field(default=10, description="Max files per analysis")
    temp_storage_path: str = Field(
        default_factory=lambda: str(Path(tempfile.gettempdir()) / "logsense"),
        description="Temp storage path",
    )
    retention_hours: int = Field(default=24, description="File retention in hours")

    # ============================================================
    # ANALYSIS
    # ============================================================

    analysis_timeout_seconds: int = Field(default=300, description="Analysis timeout")
    confidence_threshold_primary: int = Field(default=70, description="Min confidence for primary")
    confidence_threshold_alternate: int = Field(default=40, description="Min confidence for alternate")
    max_alternates: int = Field(default=5, description="Max alternate hypotheses")

    # ============================================================
    # RATE LIMITING
    # ============================================================

    rate_limit_requests_per_minute: int = Field(default=100, description="Rate limit")
    rate_limit_burst: int = Field(default=20, description="Rate limit burst")

    # ============================================================
    # LLM CONFIGURATION (Environment-Dependent)
    # ============================================================

    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    phi2_model_path: str | None = Field(default=None, description="Phi-2 model path")

    # ============================================================
    # FEATURE FLAGS (Computed from environment)
    # ============================================================

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_staging(self) -> bool:
        return self.environment == Environment.STAGING

    @property
    def llm_mode(self) -> LLMMode:
        """Determine LLM mode based on environment."""
        if self.is_production:
            return LLMMode.DISABLED
        elif self.is_development:
            return LLMMode.LOCAL
        elif self.is_staging:
            return LLMMode.CLOUD
        return LLMMode.DISABLED

    @property
    def is_llm_enabled(self) -> bool:
        return self.llm_mode != LLMMode.DISABLED

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    model_config = {
        "env_prefix": "LOGSENSE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses LRU cache for performance.
    """
    return Settings()
