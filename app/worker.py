from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from html import escape

from sqlalchemy.orm import Session

from app.config import Settings
from app.database import SessionLocal
from app.discovery.pipeline import JobDiscoveryPipeline
from app.jobs.filters import is_recent, location_matches, title_matches
from app.logging_utils import safe_exception_text
from app.matching.service import match_job
from app.models import CandidateProfile, Job, JobMatch, UserProfile
from app.telegram.notifications import (
    MessageSender,
    NotificationResult,
    notify_qualifying_match_detailed,
    send_telegram_message,
)


logger = logging.getLogger(__name__)


@dataclass
class CycleStats:
    discovered: int = 0
    filtered: int = 0
    matching_attempted: int = 0
    matched: int = 0
    rejected_by_match: int = 0
    notifications_attempted: int = 0
    notifications_sent: int = 0
    notifications_failed: int = 0

    @property
    def notified(self) -> int:
        """Backward-compatible alias used by the Telegram /search response."""
        return self.notifications_sent


class JobSearchRunner:
    def __init__(
        self,
        *,
        pipeline_factory: Callable[[], JobDiscoveryPipeline] = JobDiscoveryPipeline,
        sender: MessageSender = send_telegram_message,
        summary_sender: MessageSender | None = None,
    ) -> None:
        self.pipeline_factory = pipeline_factory
        self.sender = sender
        self.summary_sender = summary_sender or sender
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
        profile: UserProfile | None = None
        db: Session = SessionLocal()
        try:
            profile = db.get(UserProfile, profile_id)
            if not profile or (require_enabled and not profile.search_enabled):
                logger.info(
                    "PROFILE_PIPELINE_AUDIT %s",
                    json.dumps(
                        {
                            "profile_id": profile_id,
                            "profile_present": bool(profile),
                            "search_enabled": bool(profile and profile.search_enabled),
                            "failure_reason": "profile missing or search disabled",
                        }
                    ),
                )
                return stats
            if not profile.target_titles:
                logger.warning("Profile %s has no target job titles", profile_id)
                await self._send_cycle_summary(
                    profile,
                    stats,
                    failure_reason="No target job titles are configured.",
                )
                return stats

            candidate = (
                db.query(CandidateProfile)
                .filter(CandidateProfile.profile_id == profile_id)
                .first()
            )
            self._log_profile_audit(profile, candidate)
            if not candidate:
                logger.error("Profile %s has no CandidateProfile", profile_id)
                await self._send_cycle_summary(
                    profile,
                    stats,
                    failure_reason="No candidate profile is configured.",
                )
                return stats
            candidate_fields = (
                candidate.summary,
                candidate.skills,
                candidate.job_titles,
                candidate.experience,
                candidate.education,
                candidate.keywords,
            )
            if not any(value and value.strip() for value in candidate_fields):
                logger.error("CandidateProfile for profile %s is empty", profile_id)
                await self._send_cycle_summary(
                    profile,
                    stats,
                    failure_reason="The candidate profile is empty.",
                )
                return stats

            logger.info("Starting job search for profile %s", profile_id)
            pipeline = self.pipeline_factory()
            settings = Settings.from_environment()
            discovered = await pipeline.search_profile(
                db=db,
                target_titles=profile.target_titles,
                locations=profile.locations,
                remote_preference=profile.remote_preference,
                max_job_age_hours=profile.max_job_age_hours,
                limit_per_query=settings.search_results_per_query,
            )
            stats.discovered = len(discovered)

            candidates = self._candidate_jobs(db, profile_id, discovered)
            for job in candidates:
                await self._process_job(db, profile, candidate, job, stats)

            await self._send_cycle_summary(profile, stats)
            logger.info(
                "PROFILE_CYCLE_SUMMARY %s",
                json.dumps(
                    {
                        "profile_id": profile_id,
                        **asdict(stats),
                    },
                    sort_keys=True,
                ),
            )
            return stats
        except Exception as error:
            db.rollback()
            logger.exception(
                "Search cycle failed for profile %s: %s",
                profile_id,
                safe_exception_text(error),
            )
            if profile is not None:
                await self._send_cycle_summary(
                    profile,
                    stats,
                    failure_reason=f"Search cycle failed: {safe_exception_text(error)}",
                )
            return stats
        finally:
            db.close()

    async def _send_cycle_summary(
        self,
        profile: UserProfile,
        stats: CycleStats,
        *,
        failure_reason: str | None = None,
    ) -> bool:
        chat_id = str(profile.telegram_chat_id or "").strip()
        audit: dict[str, object] = {
            "profile_id": profile.id,
            "telegram_chat_id_present": bool(chat_id),
            "telegram_send_attempted": False,
            "telegram_send_success": False,
            "telegram_error": None,
        }
        if not chat_id:
            audit["telegram_error"] = "telegram_chat_id is missing"
            logger.warning(
                "TELEGRAM_SEARCH_SUMMARY %s",
                json.dumps(audit, ensure_ascii=False, sort_keys=True),
            )
            return False

        message_lines = [
            "🔎 <b>JOB SEARCH SUMMARY</b>",
            "",
            f"Profile: {profile.id}",
            f"Discovered: {stats.discovered}",
            f"Filtered: {stats.filtered}",
            f"Matching attempted: {stats.matching_attempted}",
            f"Matched: {stats.matched}",
            f"Rejected by match: {stats.rejected_by_match}",
            f"Notifications attempted: {stats.notifications_attempted}",
            f"Notifications sent: {stats.notifications_sent}",
            f"Notifications failed: {stats.notifications_failed}",
        ]
        if failure_reason:
            message_lines.extend(("", f"Status: {escape(failure_reason)}"))

        audit["telegram_send_attempted"] = True
        try:
            await self.summary_sender(chat_id, "\n".join(message_lines))
        except Exception as error:
            audit["telegram_error"] = safe_exception_text(error)
            logger.exception(
                "Telegram search-summary delivery failed for profile %s: %s",
                profile.id,
                safe_exception_text(error),
            )
            logger.error(
                "TELEGRAM_SEARCH_SUMMARY %s",
                json.dumps(audit, ensure_ascii=False, sort_keys=True),
            )
            return False

        audit["telegram_send_success"] = True
        logger.info(
            "TELEGRAM_SEARCH_SUMMARY %s",
            json.dumps(audit, ensure_ascii=False, sort_keys=True),
        )
        return True

    async def _process_job(
        self,
        db: Session,
        profile: UserProfile,
        candidate: CandidateProfile,
        job: Job,
        stats: CycleStats,
    ) -> None:
        recent_passed = is_recent(job, profile)
        title_passed = title_matches(job, profile)
        location_passed = location_matches(job, profile)
        other_filters_passed = title_passed and location_passed
        filter_reason = _filter_reason(
            recent_passed,
            title_passed,
            location_passed,
        )
        audit = _new_job_audit(
            profile,
            job,
            recent_passed,
            other_filters_passed,
            title_passed,
            location_passed,
            filter_reason,
        )

        if not recent_passed or not other_filters_passed:
            stats.filtered += 1
            audit["match"]["match_failure_reason"] = (
                f"not attempted because deterministic filter failed: {filter_reason}"
            )
            audit["notification"]["notification_failure_reason"] = (
                "job did not reach matching"
            )
            _log_job_audit(audit)
            return

        try:
            existing = (
                db.query(JobMatch)
                .filter(
                    JobMatch.profile_id == profile.id,
                    JobMatch.job_id == job.id,
                )
                .first()
            )
            if existing:
                match = existing
                qualifies = _score_passes(match.score, profile.minimum_match)
                audit["match"]["match_source"] = "cached JobMatch"
            else:
                audit["match"]["match_attempted"] = True
                stats.matching_attempted += 1
                match, qualifies = match_job(
                    db=db,
                    profile_id=profile.id,
                    job=job,
                    candidate_profile=candidate,
                    minimum_match=profile.minimum_match,
                )
                _validate_percentage_score(match.score)
                audit["match"]["match_source"] = "Groq"

            score = _validate_percentage_score(match.score)
            qualifies = score >= float(profile.minimum_match)
            audit["match"].update(
                {
                    "match_score": score,
                    "minimum_required": float(profile.minimum_match),
                    "match_passed": qualifies,
                }
            )
            if not qualifies:
                stats.rejected_by_match += 1
                audit["match"]["match_failure_reason"] = (
                    f"score {score:.2f}% is below minimum "
                    f"{profile.minimum_match}%"
                )
                audit["notification"]["notification_failure_reason"] = (
                    "match score is below minimum"
                )
                return

            stats.matched += 1
            result = await notify_qualifying_match_detailed(
                db,
                profile,
                job,
                match,
                sender=self.sender,
            )
            _apply_notification_result(audit, result)
            if result.send_attempted:
                stats.notifications_attempted += 1
                if result.send_success:
                    stats.notifications_sent += 1
                else:
                    stats.notifications_failed += 1
        except Exception as error:
            db.rollback()
            safe_error = safe_exception_text(error)
            if audit["match"]["match_attempted"]:
                stats.rejected_by_match += 1
            audit["match"]["match_failure_reason"] = safe_error
            audit["notification"]["notification_failure_reason"] = (
                "matching failed before notification eligibility"
            )
            logger.exception(
                "Job processing failed for profile %s, job %s: %s",
                profile.id,
                job.id,
                safe_error,
            )
        finally:
            _log_job_audit(audit)

    @staticmethod
    def _candidate_jobs(
        db: Session,
        profile_id: int,
        discovered: list[Job],
    ) -> list[Job]:
        candidates = list(discovered)
        seen = {job.id for job in candidates}
        backlog = (
            db.query(Job)
            .filter(Job.is_active.is_(True))
            .order_by(Job.discovered_at.desc())
            .limit(100)
            .all()
        )
        pending_jobs = (
            db.query(Job)
            .join(JobMatch, JobMatch.job_id == Job.id)
            .filter(
                JobMatch.profile_id == profile_id,
                JobMatch.notified.is_(False),
                Job.is_active.is_(True),
            )
            .all()
        )
        for job in [*backlog, *pending_jobs]:
            if job.id not in seen:
                candidates.append(job)
                seen.add(job.id)
        return candidates

    @staticmethod
    def _log_profile_audit(
        profile: UserProfile,
        candidate: CandidateProfile | None,
    ) -> None:
        fields = (
            "summary",
            "skills",
            "job_titles",
            "experience",
            "education",
            "keywords",
        )
        lengths = {
            field: len(getattr(candidate, field) or "") if candidate else 0
            for field in fields
        }
        logger.info(
            "PROFILE_PIPELINE_AUDIT %s",
            json.dumps(
                {
                    "profile_id": profile.id,
                    "resume_text_chars": len(profile.resume_text or ""),
                    "candidate_profile_present": bool(candidate),
                    "candidate_profile_field_lengths": lengths,
                    "candidate_profile_populated": bool(candidate)
                    and any(lengths.values()),
                    "minimum_match_percentage": profile.minimum_match,
                    "max_job_age_hours": profile.max_job_age_hours,
                    "telegram_chat_id_present": bool(profile.telegram_chat_id),
                },
                sort_keys=True,
            ),
        )


def _new_job_audit(
    profile: UserProfile,
    job: Job,
    recent_passed: bool,
    other_filters_passed: bool,
    title_passed: bool,
    location_passed: bool,
    filter_reason: str,
) -> dict:
    return {
        "profile_id": profile.id,
        "job": {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "url": job.apply_url,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "description_chars_passed_to_matcher": len(job.description or ""),
            "requirements_chars_passed_to_matcher": len(job.requirements or ""),
        },
        "filter": {
            "passed_recent_filter": recent_passed,
            "passed_other_filters": other_filters_passed,
            "passed_title_filter": title_passed,
            "passed_location_filter": location_passed,
            "filter_reason": filter_reason,
        },
        "match": {
            "match_attempted": False,
            "match_source": None,
            "match_score": None,
            "minimum_required": float(profile.minimum_match),
            "match_passed": False,
            "match_failure_reason": None,
        },
        "notification": {
            "notification_eligible": False,
            "telegram_chat_id_present": bool(profile.telegram_chat_id),
            "telegram_send_attempted": False,
            "telegram_send_success": False,
            "telegram_error": None,
            "notification_failure_reason": None,
        },
    }


def _apply_notification_result(audit: dict, result: NotificationResult) -> None:
    audit["notification"].update(
        {
            "notification_eligible": result.eligible,
            "telegram_chat_id_present": result.chat_id_present,
            "telegram_send_attempted": result.send_attempted,
            "telegram_send_success": result.send_success,
            "telegram_error": result.error,
            "notification_failure_reason": result.reason,
        }
    )


def _filter_reason(recent: bool, title: bool, location: bool) -> str:
    reasons = []
    if not recent:
        reasons.append("posting date is missing, invalid, or outside max_job_age_hours")
    if not title:
        reasons.append("title does not match configured target titles")
    if not location:
        reasons.append("location/remote scope does not match profile")
    return "; ".join(reasons) if reasons else "accepted"


def _validate_percentage_score(value: object) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"match score is not a percentage: {value!r}")
    try:
        score = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"match score is not numeric: {value!r}") from error
    if not math.isfinite(score):
        raise ValueError(f"match score must be finite, received {score!r}")
    if not 0 <= score <= 100:
        raise ValueError(
            f"match score must use the 0-100 percentage scale, received {score}"
        )
    return score


def _score_passes(value: object, minimum_match: int) -> bool:
    return _validate_percentage_score(value) >= float(minimum_match)


def _log_job_audit(audit: dict) -> None:
    logger.info(
        "JOB_PIPELINE_AUDIT %s",
        json.dumps(audit, ensure_ascii=False, sort_keys=True, default=str),
    )
