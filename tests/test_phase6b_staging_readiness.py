import os
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import app
from backend.app.core.rate_limiter import rate_limiter
from backend.app.providers.llm_provider import get_llm_provider, GeminiLLMProvider, MockLLMProvider
from backend.app.api.deps import get_stt_provider, get_tts_provider


# =============================================================================
# 1. Production missing DATABASE_URL is rejected
# =============================================================================
def test_production_missing_database_url_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL=None,
            ALLOWED_ORIGINS=["https://farmer-ai-advisor.vercel.app"],
            DEBUG=False,
        )
    assert "DATABASE_URL is required in production mode" in str(exc_info.value)


# =============================================================================
# 2. Production cannot silently use SQLite
# =============================================================================
def test_production_sqlite_database_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="sqlite:///./farmer_dev.db",
            ALLOWED_ORIGINS=["https://farmer-ai-advisor.vercel.app"],
            DEBUG=False,
        )
    assert "SQLite database is not permitted in production mode" in str(exc_info.value)

    # Staging also rejects SQLite
    with pytest.raises(ValidationError) as exc_info_staging:
        Settings(
            ENVIRONMENT="staging",
            DATABASE_URL="sqlite:///./test.db",
            ALLOWED_ORIGINS=["https://staging.farmer-ai-advisor.vercel.app"],
        )
    assert "SQLite database is not permitted in staging mode" in str(exc_info_staging.value)


# =============================================================================
# 3. Development retains intended local fallback behavior
# =============================================================================
def test_development_retains_local_fallback_behavior():
    dev_settings = Settings(
        ENVIRONMENT="development",
        DATABASE_URL=None,
        ALLOWED_ORIGINS=["http://localhost:3000"],
        DEBUG=True,
    )
    assert dev_settings.ENVIRONMENT == "development"
    assert dev_settings.DATABASE_URL is None
    assert dev_settings.DEBUG is True


# =============================================================================
# 4. Production CORS cannot use unrestricted wildcard '*'
# =============================================================================
def test_production_cors_wildcard_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://postgres:pass@db.supabase.co:5432/postgres",
            ALLOWED_ORIGINS=["*"],
            DEBUG=False,
        )
    assert "Wildcard '*' is strictly prohibited" in str(exc_info.value)

    # Valid comma-separated origins parsed correctly in production
    valid_prod = Settings(
        ENVIRONMENT="production",
        DATABASE_URL="postgresql://postgres:pass@db.supabase.co:5432/postgres",
        ALLOWED_ORIGINS="https://farmer-ai.vercel.app, https://staging.farmer-ai.vercel.app",
        DEBUG=False,
    )
    assert len(valid_prod.ALLOWED_ORIGINS) == 2
    assert "https://farmer-ai.vercel.app" in valid_prod.ALLOWED_ORIGINS
    assert "https://staging.farmer-ai.vercel.app" in valid_prod.ALLOWED_ORIGINS


# =============================================================================
# 5. Production cannot run with DEBUG=True
# =============================================================================
def test_production_debug_true_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql://postgres:pass@db.supabase.co:5432/postgres",
            ALLOWED_ORIGINS=["https://farmer-ai.vercel.app"],
            DEBUG=True,
        )
    assert "DEBUG must be set to False in production mode" in str(exc_info.value)


# =============================================================================
# 6. Production requires real provider credentials and refuses silent mock fallback
# =============================================================================
def test_production_refuses_silent_mock_llm_fallback(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.app.core.config.settings.GEMINI_API_KEY", None)
    monkeypatch.setattr("backend.app.core.config.settings.LLM_API_KEY", None)

    with pytest.raises(ValueError, match="GEMINI_API_KEY is required in production mode"):
        get_llm_provider(mock_for_test=False)


def test_production_refuses_unauthenticated_voice_providers(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.app.core.config.settings.SARVAM_API_KEY", None)

    with pytest.raises(ValueError, match="SARVAM_API_KEY is required in production mode for Speech-to-Text"):
        get_stt_provider()

    with pytest.raises(ValueError, match="SARVAM_API_KEY is required in production mode for Text-to-Speech"):
        get_tts_provider()


# =============================================================================
# 7. Frontend configuration and secret isolation audit
# =============================================================================
def test_frontend_backend_url_and_secret_isolation():
    # Verify frontend/.env.example exists and only references NEXT_PUBLIC_BACKEND_URL
    frontend_env_example = os.path.join(os.path.dirname(__file__), "..", "frontend", ".env.example")
    assert os.path.exists(frontend_env_example)

    with open(frontend_env_example, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify only NEXT_PUBLIC_BACKEND_URL is defined as an active variable
    active_lines = [
        line.strip() for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(active_lines) == 1
    assert active_lines[0].startswith("NEXT_PUBLIC_BACKEND_URL=")

    for line in active_lines:
        var_name = line.split("=")[0].strip()
        for forbidden in ["GEMINI", "SARVAM", "DATA_GOV_IN", "DATABASE_URL", "SERVICE_ROLE", "SECRET"]:
            assert forbidden not in var_name


# =============================================================================
# 8. Existing rate limiting and security hardening remain intact
# =============================================================================
def test_rate_limiting_and_health_remain_intact():
    client = TestClient(app)
    # Health endpoint works and has rate limiting headers
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["service"] == "farmer-ai-backend"
    assert data["version"] == "0.1.0"
    assert data["database"] in ("connected", "disconnected")
    assert data["environment"] == "development"
    assert "X-RateLimit-Limit" in res.headers
    assert res.headers["X-RateLimit-Limit"] == "60"


def test_trust_proxy_headers_safe_default():
    settings = Settings()
    assert settings.TRUST_PROXY_HEADERS is False

