from groq import Groq

from app.config import Settings


def get_groq_client() -> Groq:
    """Build the client lazily so offline commands can import the app."""
    api_key = Settings.from_environment().groq_api_key
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=api_key)
