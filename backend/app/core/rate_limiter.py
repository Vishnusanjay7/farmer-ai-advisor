import math
import time
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional, Callable, List
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.app.core.config import settings
from backend.app.core.logging import logger

# ==============================================================================
# RATE LIMIT SPECIFICATION (Hackathon Controlled Instance-Local Protection)
# ==============================================================================
# Endpoint: (HTTP_METHOD, PATH) -> Max Requests per 60 seconds
DEFAULT_RATE_LIMITS: Dict[Tuple[str, str], int] = {
    ("POST", "/api/v1/voice/stt"): 10,
    ("POST", "/api/v1/voice/tts"): 10,
    ("POST", "/api/v1/advisor/query"): 20,
    ("GET", "/api/v1/mandi/prices"): 30,
    ("GET", "/api/v1/health"): 60,
}


def resolve_client_ip(request: Request, trust_proxy_headers: bool = False) -> str:
    """
    Safely resolves the client IP address.

    Proxy Strategy & Limitations:
    - If trust_proxy_headers is True (e.g. running behind a verified reverse proxy like Render or Railway),
      the leftmost IP from the X-Forwarded-For header is used as the original client address.
    - If trust_proxy_headers is False, X-Forwarded-For is strictly ignored to prevent IP spoofing,
      and the client address is derived directly from the underlying TCP socket connection (request.client.host).
    - If request.client is None (e.g. some internal mock transports), defaults to '127.0.0.1'.
    """
    if trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            client_ip = xff.split(",")[0].strip()
            if client_ip:
                return client_ip

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"


class InMemoryRateLimiter:
    """
    Thread-safe instance-local in-memory sliding window rate limiter.
    Enforces per-minute request quotas per client IP on designated endpoints.
    Provides automatic expiration of stale buckets and bounded memory management.
    """

    def __init__(
        self,
        limits: Optional[Dict[Tuple[str, str], int]] = None,
        window_seconds: float = 60.0,
        max_tracked_keys: int = 10000,
        time_func: Optional[Callable[[], float]] = None,
    ):
        self.limits = limits or DEFAULT_RATE_LIMITS
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self._time_func = time_func or time.time
        # Key: "METHOD:PATH:CLIENT_IP" -> deque of request timestamps
        self._buckets: Dict[str, deque] = defaultdict(deque)
        self._last_cleanup = self.get_time()

    def get_time(self) -> float:
        return self._time_func()

    def set_time_func(self, time_func: Optional[Callable[[], float]]):
        self._time_func = time_func or time.time

    def reset(self):
        """Clears all tracking buckets and resets the time function to standard wall clock."""
        self._buckets.clear()
        self._time_func = time.time
        self._last_cleanup = self.get_time()

    def _cleanup_stale_buckets(self, now: float):
        """Purges buckets with no requests in the active window to prevent unbounded memory growth."""
        cutoff = now - self.window_seconds
        stale_keys = [k for k, timestamps in self._buckets.items() if not timestamps or timestamps[-1] < cutoff]
        for k in stale_keys:
            del self._buckets[k]

        # Enforce hard upper bound on tracked keys
        if len(self._buckets) > self.max_tracked_keys:
            sorted_keys = sorted(
                self._buckets.keys(),
                key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0.0,
            )
            excess = len(self._buckets) - self.max_tracked_keys
            for k in sorted_keys[:excess]:
                del self._buckets[k]

    def check_rate_limit(
        self, method: str, path: str, client_ip: str
    ) -> Tuple[bool, int, int, int]:
        """
        Evaluates whether a request should be permitted.

        Returns:
            (allowed: bool, limit: int, remaining: int, retry_after: int)
        """
        normalized_path = path.rstrip("/") or "/"
        limit = self.limits.get((method.upper(), normalized_path))

        if limit is None:
            # Endpoint is not rate-limited
            return True, -1, -1, 0

        now = self.get_time()
        bucket_key = f"{method.upper()}:{normalized_path}:{client_ip}"
        cutoff = now - self.window_seconds

        # Periodic cleanup of expired entries
        if (now - self._last_cleanup > self.window_seconds) or (len(self._buckets) > self.max_tracked_keys):
            self._cleanup_stale_buckets(now)
            self._last_cleanup = now

        timestamps = self._buckets[bucket_key]

        # Evict timestamps outside the sliding window
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= limit:
            oldest = timestamps[0]
            retry_after = max(1, math.ceil(oldest + self.window_seconds - now))
            return False, limit, 0, retry_after

        # Record this request
        timestamps.append(now)
        remaining = max(0, limit - len(timestamps))
        return True, limit, remaining, 0


# Global singleton instance for application runtime
rate_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI HTTP middleware applying instance-local sliding window rate limiting.
    Returns HTTP 429 with RFC7807 problem detail when limits are exceeded.
    """

    def __init__(
        self,
        app,
        limiter: Optional[InMemoryRateLimiter] = None,
        trust_proxy_headers: Optional[bool] = None,
    ):
        super().__init__(app)
        self.limiter = limiter or rate_limiter
        self.trust_proxy_headers = (
            trust_proxy_headers
            if trust_proxy_headers is not None
            else getattr(settings, "TRUST_PROXY_HEADERS", False)
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check global kill switch
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return await call_next(request)

        client_ip = resolve_client_ip(request, trust_proxy_headers=self.trust_proxy_headers)
        method = request.method
        path = request.url.path

        allowed, limit, remaining, retry_after = self.limiter.check_rate_limit(
            method=method, path=path, client_ip=client_ip
        )

        if not allowed:
            logger.warning(
                f"Rate limit exceeded for client {client_ip} on {method} {path} "
                f"(limit: {limit}/min, retry_after: {retry_after}s)"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "status_code": 429,
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {limit} requests per minute exceeded. Please try again after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        response = await call_next(request)

        if limit > 0:
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
