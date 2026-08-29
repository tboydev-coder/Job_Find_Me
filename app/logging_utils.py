from __future__ import annotations

from app.config import Settings


def safe_exception_text(error: BaseException) -> str:
    """Return a useful exception without leaking configured credentials."""
    text = f"{type(error).__name__}: {error}"
    settings = Settings.from_environment()
    for secret in (
        settings.telegram_bot_token,
        settings.groq_api_key,
        settings.tavily_api_key,
    ):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:4000]


def safe_response_excerpt(value: object, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value)
    settings = Settings.from_environment()
    for secret in (
        settings.telegram_bot_token,
        settings.groq_api_key,
        settings.tavily_api_key,
    ):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:limit]
