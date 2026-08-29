from __future__ import annotations

import argparse
import logging
from urllib.parse import urlparse

from app.database import SessionLocal
from app.discovery.extractor import is_disallowed_job_url, is_job_listing_page
from app.models import Job


logger = logging.getLogger(__name__)

BAD_HOSTS = {"reddit.com", "youtube.com", "youtu.be"}
BAD_TITLE_PHRASES = {
    "career advice",
    "how to become",
    "in-demand skills",
    "interview questions",
    "job description template",
    "jobs in lagos",
    "salary guide",
    "tutorial",
}
BAD_URL_PHRASES = {
    "/career-advice/",
    "/categories/",
    "/jobs-by-title/",
    "/job-search/",
}


def invalid_job_reason(job: Job) -> str | None:
    title = " ".join((job.title or "").lower().split())
    url = (job.source_url or job.apply_url or "").lower()
    host = (urlparse(url).hostname or "").removeprefix("www.")
    if any(host == value or host.endswith(f".{value}") for value in BAD_HOSTS):
        return f"blocked host: {host}"
    phrase = next((value for value in BAD_TITLE_PHRASES if value in title), None)
    if phrase:
        return f"non-job title phrase: {phrase}"
    pattern = next((value for value in BAD_URL_PHRASES if value in url), None)
    if pattern:
        return f"listing/article URL: {pattern}"
    if is_job_listing_page(url) or is_disallowed_job_url(url):
        return "generic listing, article, or disallowed URL"
    if not (job.apply_url or "").lower().startswith(("http://", "https://")):
        return "invalid application URL"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or deactivate clearly invalid legacy job records."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Deactivate the records shown by the preview (never deletes them).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    db = SessionLocal()
    try:
        candidates = []
        for job in db.query(Job).filter(Job.is_active.is_(True)).all():
            reason = invalid_job_reason(job)
            if reason:
                candidates.append((job, reason))
                logger.info("%s | %s | %s", job.id, reason, job.title)

        if not args.apply:
            logger.info(
                "Preview only: %s job(s) would be deactivated. Re-run with --apply to proceed.",
                len(candidates),
            )
            return

        for job, _reason in candidates:
            job.is_active = False
        db.commit()
        logger.info("Deactivated %s invalid job(s). Records remain recoverable.", len(candidates))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
