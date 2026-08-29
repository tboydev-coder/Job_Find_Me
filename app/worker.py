from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.database import SessionLocal
from app.discovery.pipeline import JobDiscoveryPipeline
from app.jobs.filters import job_matches_profile
from app.matching.service import match_job
from app.models import CandidateProfile, Job, JobMatch, UserProfile
from app.telegram.notifications import MessageSender, notify_qualifying_match, send_telegram_message


logger = logging.getLogger(__name__)


@dataclass
class CycleStats:
    discovered: int = 0
    filtered: int = 0
    matched: int = 0
    notified: int = 0


class JobSearchRunner:
    def __init__(
        self,
        *,
        pipeline_factory: Callable[[], JobDiscoveryPipeline] = JobDiscoveryPipeline,
        sender: MessageSender = send_telegram_message,
    ) -> None:
        self.pipeline_factory = pipeline_factory
        self.sender = sender
        self._locks: dict[int, asyncio.Lock] = {}

    async def run_profile(
        self,
        profile_id: int,
        *,
        require_enabled: bool = True,
    ) -> CycleStats:
        lock = self._locks.setdefault(profile_id, asyncio.Lock())
        if lock.locked():
            logger.info("Search already running for profile %s", profile_id)
            return CycleStats()

        async with lock:
            return await self._run_profile(profile_id, require_enabled=require_enabled)

    async def _run_profile(
        self,
        profile_id: int,
        *,
        require_enabled: bool,
    ) -> CycleStats:
        stats = CycleStats()
        db: Session = SessionLocal()
        try:
            profile = db.get(UserProfile, profile_id)
            if not profile or (require_enabled and not profile.search_enabled):
                return stats
            if not profile.target_titles:
                logger.warning("Profile %s has no target job titles", profile_id)
                return stats

            candidate = (
                db.query(CandidateProfile)
                .filter(CandidateProfile.profile_id == profile_id)
                .first()
            )
            if not candidate:
                logger.warning("Profile %s has no CandidateProfile", profile_id)
                return stats

            logger.info("Starting job search for profile %s", profile_id)
            stats.notified += await self._retry_pending(db, profile)
            pipeline = self.pipeline_factory()
            settings = Settings.from_environment()
            discovered = await pipeline.search_profile(
                db=db,
                target_titles=profile.target_titles,
                locations=profile.locations,
                remote_preference=profile.remote_preference,
                limit_per_query=settings.search_results_per_query,
            )
            stats.discovered = len(discovered)

            candidates = self._unmatched_candidates(db, profile_id, discovered)
            for job in candidates:
                if not job_matches_profile(job, profile):
                    stats.filtered += 1
                    continue
                try:
                    match, qualifies = match_job(
                        db=db,
                        profile_id=profile.id,
                        job=job,
                        candidate_profile=candidate,
                        minimum_match=profile.minimum_match,
                    )
                    stats.matched += 1
                    if qualifies and await notify_qualifying_match(
                        db,
                        profile,
                        job,
                        match,
                        sender=self.sender,
                    ):
                        stats.notified += 1
                except Exception:
                    db.rollback()
                    logger.exception("Matching failed for job %s", job.id)

            logger.info(
                "Search complete for profile %s: discovered=%s filtered=%s matched=%s notified=%s",
                profile_id,
                stats.discovered,
                stats.filtered,
                stats.matched,
                stats.notified,
            )
            return stats
        except Exception:
            db.rollback()
            logger.exception("Search cycle failed for profile %s", profile_id)
            return stats
        finally:
            db.close()

    @staticmethod
    def _unmatched_candidates(
        db: Session,
        profile_id: int,
        discovered: list[Job],
    ) -> list[Job]:
        matched_job_ids = {
            job_id
            for (job_id,) in db.query(JobMatch.job_id)
            .filter(JobMatch.profile_id == profile_id)
            .all()
        }
        candidates = [job for job in discovered if job.id not in matched_job_ids]
        seen = {job.id for job in candidates}
        backlog = (
            db.query(Job)
            .filter(Job.is_active.is_(True), ~Job.id.in_(matched_job_ids))
            .order_by(Job.discovered_at.desc())
            .limit(100)
            .all()
        )
        for job in backlog:
            if job.id not in seen:
                candidates.append(job)
                seen.add(job.id)
        return candidates

    async def _retry_pending(self, db: Session, profile: UserProfile) -> int:
        pending = (
            db.query(JobMatch, Job)
            .join(Job, Job.id == JobMatch.job_id)
            .filter(
                JobMatch.profile_id == profile.id,
                JobMatch.notified.is_(False),
                JobMatch.score >= profile.minimum_match,
                Job.is_active.is_(True),
            )
            .all()
        )
        sent = 0
        for match, job in pending:
            if await notify_qualifying_match(
                db,
                profile,
                job,
                match,
                sender=self.sender,
            ):
                sent += 1
        return sent
