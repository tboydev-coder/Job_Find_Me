import os
import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Job, JobMatch, UserProfile

from .notifications import notify_qualifying_match


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.profile = UserProfile(
            telegram_chat_id=123,
            minimum_match=75,
            max_notifications_per_day=50,
        )
        self.job = Job(
            source="test",
            title="Backend Engineer",
            location="Remote",
            apply_url="https://example.com/apply/2",
            content_hash="c" * 64,
        )
        self.db.add_all([self.profile, self.job])
        self.db.commit()

    async def asyncTearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def make_match(self, score: float = 85, notified: bool = False) -> JobMatch:
        match = JobMatch(
            profile_id=self.profile.id,
            job_id=self.job.id,
            score=score,
            skills_score=85,
            experience_score=80,
            title_score=90,
            education_score=80,
            location_score=100,
            matched_skills=["Python"],
            missing_skills=["AWS"],
            explanation="Good fit.",
            notified=notified,
        )
        self.db.add(match)
        self.db.commit()
        return match

    async def test_qualifying_match_sends_and_is_marked(self) -> None:
        match = self.make_match()
        sender = AsyncMock()
        sent = await notify_qualifying_match(
            self.db, self.profile, self.job, match, sender=sender
        )
        self.assertTrue(sent)
        self.assertTrue(match.notified)
        self.assertIsNotNone(match.notified_at)
        sender.assert_awaited_once()

    async def test_below_threshold_and_notified_match_do_not_send(self) -> None:
        sender = AsyncMock()
        low_match = self.make_match(score=74.9)
        self.assertFalse(
            await notify_qualifying_match(
                self.db, self.profile, self.job, low_match, sender=sender
            )
        )
        low_match.score = 90
        low_match.notified = True
        self.assertFalse(
            await notify_qualifying_match(
                self.db, self.profile, self.job, low_match, sender=sender
            )
        )
        sender.assert_not_awaited()

    async def test_telegram_failure_does_not_mark_notified(self) -> None:
        match = self.make_match()
        sender = AsyncMock(side_effect=RuntimeError("temporary failure"))
        with patch("app.telegram.notifications.logger.exception"):
            sent = await notify_qualifying_match(
                self.db, self.profile, self.job, match, sender=sender
            )
        self.assertFalse(sent)
        self.assertFalse(match.notified)
        self.assertIsNone(match.notified_at)

    async def test_daily_limit_counts_only_successful_notifications(self) -> None:
        self.profile.max_notifications_per_day = 1
        first_match = self.make_match(notified=True)
        first_match.notified_at = datetime.now()
        second_job = Job(
            source="test",
            title="Python Engineer",
            location="Remote",
            apply_url="https://example.com/apply/3",
            content_hash="d" * 64,
        )
        self.db.add(second_job)
        self.db.commit()
        second_match = JobMatch(
            profile_id=self.profile.id,
            job_id=second_job.id,
            score=90,
            skills_score=90,
            experience_score=90,
            title_score=90,
            education_score=90,
            location_score=90,
            matched_skills=[],
            missing_skills=[],
            notified=False,
        )
        self.db.add(second_match)
        self.db.commit()
        sender = AsyncMock()
        sent = await notify_qualifying_match(
            self.db,
            self.profile,
            second_job,
            second_match,
            sender=sender,
        )
        self.assertFalse(sent)
        self.assertFalse(second_match.notified)
        sender.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
