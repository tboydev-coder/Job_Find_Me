from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    tavily_api_key: str | None
    groq_api_key: str | None
    groq_model: str
    telegram_bot_token: str | None
    resume_storage_dir: Path
    search_results_per_query: int
    scheduler_poll_seconds: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            tavily_api_key=os.getenv("TAVILY_API_KEY"),
            groq_api_key=os.getenv("GROQ_API_KEY"),
            groq_model=os.getenv(
                "GROQ_MODEL",
                "openai/gpt-oss-20b",
            ),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            resume_storage_dir=Path(
                os.getenv("RESUME_STORAGE_DIR", "storage/resumes")
            ),
            search_results_per_query=_positive_int(
                "SEARCH_RESULTS_PER_QUERY",
                default=5,
            ),
            scheduler_poll_seconds=_positive_int(
                "SCHEDULER_POLL_SECONDS",
                default=30,
            ),
        )

    def validate_worker(self) -> None:
        required = {
            "DATABASE_URL": self.database_url,
            "TAVILY_API_KEY": self.tavily_api_key,
            "GROQ_API_KEY": self.groq_api_key,
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing)
            )


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value
