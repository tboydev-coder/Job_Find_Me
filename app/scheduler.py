from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.database import SessionLocal
from app.models import UserProfile
from app.worker import JobSearchRunner


logger = logging.getLogger(__name__)


class ProfileScheduler:
    def __init__(self, runner: JobSearchRunner) -> None:
        self.runner = runner
        self._next_runs: dict[int, datetime] = {}

    async def run_forever(self) -> None:
        poll_seconds = Settings.from_environment().scheduler_poll_seconds
        logger.info("Profile scheduler started")
        while True:
            try:
                due_profiles = self._due_profiles()
                for profile_id in due_profiles:
                    await self.runner.run_profile(profile_id)
            except asyncio.CancelledError:
                logger.info("Profile scheduler stopped")
                raise
            except Exception:
                logger.exception("Scheduler iteration failed")
            await asyncio.sleep(poll_seconds)

    def _due_profiles(self) -> list[int]:
        db = SessionLocal()
        try:
            profiles = (
                db.query(UserProfile)
                .filter(UserProfile.search_enabled.is_(True))
                .all()
            )
            now = datetime.now(timezone.utc)
            active_ids = {profile.id for profile in profiles}
            self._next_runs = {
                profile_id: due_at
                for profile_id, due_at in self._next_runs.items()
                if profile_id in active_ids
            }
            due: list[int] = []
            for profile in profiles:
                next_run = self._next_runs.get(profile.id, now)
                if now >= next_run:
                    due.append(profile.id)
                    interval = max(1, profile.search_interval_minutes)
                    self._next_runs[profile.id] = now + timedelta(minutes=interval)
            return due
        finally:
            db.close()
