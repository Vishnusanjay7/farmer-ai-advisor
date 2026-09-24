from backend.app.core.config import settings, Settings


def test_settings_loading_and_defaults():
    """Verify that settings load with valid defaults and expected types."""
    assert settings.APP_NAME == "Farmer AI Advisory Backend"
    assert settings.APP_VERSION == "0.1.0"
    assert isinstance(settings.ALLOWED_ORIGINS, list)
    assert len(settings.ALLOWED_ORIGINS) > 0
    assert settings.EMBEDDING_DIMENSION == 768


def test_custom_settings_instance():
    """Verify that Settings can be instantiated with custom values."""
    custom = Settings(APP_NAME="Test Kisan App", LOG_LEVEL="DEBUG")
    assert custom.APP_NAME == "Test Kisan App"
    assert custom.LOG_LEVEL == "DEBUG"
