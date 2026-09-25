import os
from typing import List, Optional, Any
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Configuration
    APP_NAME: str = "Farmer AI Advisory Backend"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="development | staging | production")
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server Configuration
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://farmer-ai-advisor.vercel.app",
    ]

    # Supabase / PostgreSQL Configuration
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection string. In dev, falls back to SQLite or mock if unset.",
    )
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None

    # Voice Providers (Sarvam AI)
    SARVAM_API_KEY: Optional[str] = None
    SARVAM_STT_ENDPOINT: str = "https://api.sarvam.ai/speech-to-text"
    SARVAM_TTS_ENDPOINT: str = "https://api.sarvam.ai/text-to-speech"

    # Government Data APIs
    DATA_GOV_IN_API_KEY: Optional[str] = None
    AGMARKNET_RESOURCE_ID: str = "9ef84268-d588-465a-a308-a864a43d0070"
    AGMARKNET_CACHE_TTL_SECONDS: int = 21600  # 6 hours default TTL


    # LLM & Embeddings Provider
    LLM_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-3.8-flash"
    LLM_FALLBACK_MODEL: Optional[str] = "gemini-3.5-flash"
    LLM_MAX_RETRIES: int = 1
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768
    RAG_TOP_K: int = 4
    RAG_SIMILARITY_THRESHOLD: float = 0.55

    # Rate Limiting & Proxy Configuration
    RATE_LIMIT_ENABLED: bool = True
    TRUST_PROXY_HEADERS: bool = False

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        if self.ENVIRONMENT in ("production", "staging"):
            # 1. DATABASE_URL must be provided and must be PostgreSQL
            if not self.DATABASE_URL:
                raise ValueError(
                    f"DATABASE_URL is required in {self.ENVIRONMENT} mode. "
                    "Cannot fall back to local SQLite database in production/staging."
                )
            if "sqlite" in self.DATABASE_URL.lower():
                raise ValueError(
                    f"SQLite database is not permitted in {self.ENVIRONMENT} mode. "
                    "A valid PostgreSQL/Supabase connection string is required."
                )

            # 2. CORS wildcard is prohibited in production and staging
            if any(origin.strip() == "*" for origin in self.ALLOWED_ORIGINS):
                raise ValueError(
                    f"Wildcard '*' is strictly prohibited in ALLOWED_ORIGINS in {self.ENVIRONMENT} mode."
                )

            # 3. Production cannot run with DEBUG=True
            if self.ENVIRONMENT == "production" and self.DEBUG:
                raise ValueError("DEBUG must be set to False in production mode.")

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
