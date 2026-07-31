import logging
from typing import Optional
from fastapi import Request, HTTPException, status
from app.config import settings

logger = logging.getLogger("tiktok_story_api.auth")


class AuthException(HTTPException):
    def __init__(self, status_code: int, error_message: str):
        super().__init__(status_code=status_code, detail={"success": False, "error": error_message})


def mask_key(key: str) -> str:
    """Mask sensitive API keys for safe logging."""
    if not key:
        return ""
    if len(key) <= 6:
        return "***"
    return f"{key[:2]}***{key[-3:]}"


async def verify_api_key(request: Request) -> str:
    """
    Validates incoming request authentication.
    Accepts either 'X-API-Key: YOUR_KEY' header or 'Authorization: Bearer YOUR_KEY'.
    """
    api_key: Optional[str] = request.headers.get("X-API-Key")

    if not api_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()

    if not api_key:
        logger.warning("API key missing in request")
        raise AuthException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_message="API key is missing"
        )

    valid_keys = settings.get_api_keys()

    # If no API keys configured in settings, reject requests for security
    if not valid_keys or api_key not in valid_keys:
        logger.warning(f"Invalid API key supplied: {mask_key(api_key)}")
        raise AuthException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_message="Invalid API key"
        )

    logger.debug(f"Authenticated request with key {mask_key(api_key)}")
    return api_key
