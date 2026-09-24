import pytest
from backend.app.core.rate_limiter import rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter_state():
    """Ensures each test function executes with a fresh in-memory rate limiter bucket state."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()
