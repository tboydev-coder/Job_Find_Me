from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.jobs.repository import save_or_get_job
from app.models import Job

from .extractor import (
    JobPageExtractor,
    convert_job_posting,
    extract_fallback_job,
    extract_json_ld,
    find_job_posting,
    is_job_listing_page,
    is_disallowed_job_url,
)
from .query_builder import build_job_queries
from .search import SearchProvider
from .tavily_provider import TavilySearchProvider


logger = logging.getLogger(__name__)


class JobDiscoveryPipeline:
    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        extractor: JobPageExtractor | None = None,
    ) -> None:
        self.search_provider = search_provider or TavilySearchProvider()
        self.extractor = extractor or JobPageExtractor()

    async def search_and_save(
        self,
        db: Session,
        query: str,
        limit: int = 10,
        time_range: str | None = None,
    ) -> list[Job]:
        logger.info("Search query: %s (time_range=%s)", query, time_range)
        results = await self.search_provider.search(
            query=query,
            limit=limit,
            time_range=time_range,
        )
        logger.info("Search results: %s", len(results))

        jobs: list[Job] = []
        seen_ids: set[int] = set()
        for result in results:
            if not result.url.lower().startswith(("http://", "https://")):
                logger.warning("Ignoring invalid result URL: %s", result.url)
                continue
            if is_job_listing_page(result.url) or is_disallowed_job_url(result.url):
                logger.info("Rejected job listing/search page: %s", result.url)
                continue
            try:
                html = await self.extractor.fetch(result.url)
                posting = find_job_posting(extract_json_ld(html))
                if posting:
                    job_data = convert_job_posting(posting, result.url)
                else:
                    job_data = extract_fallback_job(
                        html=html,
                        source_url=result.url,
                    )
                if not job_data:
                    logger.info("Rejected non-job page: %s", result.url)
                    continue

                job, created = save_or_get_job(db, job_data)
                if job.id not in seen_ids:
                    jobs.append(job)
                    seen_ids.add(job.id)
                logger.info(
                    "%s job: %s (%s)",
                    "Saved" if created else "Duplicate",
                    job.title,
                    result.url,
                )
            except httpx.HTTPStatusError as error:
                logger.warning(
                    "Job page returned HTTP %s: %s",
                    error.response.status_code,
                    result.url,
                )
            except (httpx.HTTPError, ValueError) as error:
                logger.warning("Could not process %s: %s", result.url, error)
            except Exception:
                db.rollback()
                logger.exception("Unexpected discovery failure for %s", result.url)
        return jobs

    async def search_profile(
        self,
        db: Session,
        target_titles: str,
        locations: str | None = None,
        remote_preference: str | None = None,
        max_job_age_hours: int | None = None,
        limit_per_query: int = 5,
    ) -> list[Job]:
        queries = build_job_queries(
            target_titles=target_titles,
            locations=locations,
            remote_preference=remote_preference,
            max_job_age_hours=max_job_age_hours,
        )
        time_range = _tavily_time_range(max_job_age_hours)
        all_jobs: list[Job] = []
        seen_ids: set[int] = set()
        for query in queries:
            try:
                jobs = await self.search_and_save(
                    db=db,
                    query=query,
                    limit=limit_per_query,
                    time_range=time_range,
                )
                for job in jobs:
                    if job.id not in seen_ids:
                        all_jobs.append(job)
                        seen_ids.add(job.id)
            except Exception:
                db.rollback()
                logger.exception("Search failed for query: %s", query)
        logger.info("Valid unique jobs discovered: %s", len(all_jobs))
        return all_jobs


def _tavily_time_range(max_job_age_hours: int | None) -> str | None:
    if max_job_age_hours is None:
        return None
    if max_job_age_hours <= 24:
        return "day"
    if max_job_age_hours <= 24 * 7:
        return "week"
    if max_job_age_hours <= 24 * 31:
        return "month"
    if max_job_age_hours <= 24 * 366:
        return "year"
    return None
