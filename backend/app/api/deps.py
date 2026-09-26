from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.schemas.advisor import AuthUser
from backend.app.providers.base import SpeechToTextProvider, TextToSpeechProvider
from backend.app.providers.stt_provider import SarvamSTTProvider
from backend.app.providers.tts_provider import SarvamTTSProvider

security = HTTPBearer(auto_error=False)


def decode_jwt_token(token: str) -> Optional[dict]:
    """Decodes and validates a Supabase JWT token."""
    if not token or not token.strip():
        return None

    token = token.strip()

    # Support testing mock tokens (e.g. 'test-user-a', 'mock-user-123')
    if token.startswith("test-") or token.startswith("mock-"):
        uid = token.split(":", 1)[1] if ":" in token else token
        return {
            "sub": uid,
            "email": f"{uid}@example.com",
            "user_metadata": {"full_name": f"User {uid}"},
            "role": "authenticated",
        }

    try:
        # If secret is configured, verify HMAC signature
        jwt_secret = getattr(settings, "SUPABASE_JWT_SECRET", None)
        if jwt_secret:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            return payload
        else:
            # Fallback to decoding claims without signature verification in dev/staging/test
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": True},
            )
            return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired.")
        return None
    except Exception as e:
        logger.warning(f"Failed to decode JWT token: {e}")
        return None


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[AuthUser]:
    """Dependency that returns the authenticated AuthUser if valid token is provided, else None."""
    if not credentials or not credentials.credentials:
        return None

    payload = decode_jwt_token(credentials.credentials)
    if not payload:
        return None

    user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
    if not user_id:
        return None

    email = payload.get("email")
    metadata = payload.get("user_metadata", {}) or {}
    full_name = metadata.get("full_name") or metadata.get("name") or (email.split("@")[0] if email else None)

    return AuthUser(
        id=str(user_id),
        email=email,
        full_name=full_name,
        role=payload.get("role", "authenticated"),
    )


async def get_current_user(
    user: Optional[AuthUser] = Depends(get_current_user_optional),
) -> AuthUser:
    """Dependency that requires authentication. Raises 401 if unauthenticated."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Authentication required. Please provide a valid Bearer token."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_stt_provider() -> SpeechToTextProvider:
    """Dependency provider returning configured STT provider."""
    if settings.ENVIRONMENT in ("production", "staging") and not settings.SARVAM_API_KEY:
        raise ValueError(
            f"SARVAM_API_KEY is required in {settings.ENVIRONMENT} mode for Speech-to-Text."
        )
    return SarvamSTTProvider(api_key=settings.SARVAM_API_KEY)


def get_tts_provider() -> TextToSpeechProvider:
    """Dependency provider returning configured TTS provider."""
    if settings.ENVIRONMENT in ("production", "staging") and not settings.SARVAM_API_KEY:
        raise ValueError(
            f"SARVAM_API_KEY is required in {settings.ENVIRONMENT} mode for Text-to-Speech."
        )
    return SarvamTTSProvider(api_key=settings.SARVAM_API_KEY)
