from __future__ import annotations

import logging

from sqlalchemy import text

from app.config import Settings
from app.database import engine
from app.scheduler import ProfileScheduler
from app.telegram.bot import create_bot
from app.worker import JobSearchRunner


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    settings = Settings.from_environment()
    settings.validate_worker()

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("Database connection verified")
    logger.info("Starting Job-Find-Me with Groq model %s", settings.groq_model)

    runner = JobSearchRunner()
    scheduler = ProfileScheduler(runner)
    application = create_bot(runner=runner, scheduler=scheduler)
    application.run_polling()


if __name__ == "__main__":
    main()
