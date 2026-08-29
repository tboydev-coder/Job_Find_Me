import os
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.matching.schemas import JobMatchAnalysis
from app.models import CandidateProfile, Job, JobMatch, UserProfile
from app.worker import JobSearchRunner


class FakePipeline:
    async def search_profile(self, db, **_kwargs):
        return db.query(Job).all()


class WorkerEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        profile = UserProfile(
            telegram_chat_id=123,
            target_titles="Backend Developer",
            locations="Nigeria, Remote",
            remote_preference="preferred",
            minimum_match=75,
            max_job_age_hours=24,
            search_enabled=True,
        )
        db.add(profile)
        db.commit()
        self.profile_id = profile.id
        db.add(
            CandidateProfile(
                profile_id=profile.id,
                summary="Backend engineer",
                skills="Python, PostgreSQL",
                job_titles="Backend Developer",
                experience="Three years",
                education="BSc",
                keywords="API",
            )
        )
        db.add(
            Job(
                source="test",
                title="Backend Engineer",
                company="Acme",
                location="Lagos, Nigeria",
                description="Build APIs",
                requirements="Python",
                apply_url="https://example.com/apply/worker",
                posted_at=datetime.now() - timedelta(hours=1),
                content_hash="e" * 64,
            )
        )
        db.commit()
        db.close()

    async def asyncTearDown(self) -> None:
        self.engine.dispose()

    async def test_search_filter_match_persist_and_notify(self) -> None:
        sender = AsyncMock()
        summary_sender = AsyncMock()
        analysis = JobMatchAnalysis(
            overall_score=82.5,
            skills_score=90,
            experience_score=85,
            title_score=95,
            education_score=80,
            location_score=100,
            matched_skills=["Python"],
            missing_skills=[],
            explanation="Strong match.",
        )
        runner = JobSearchRunner(
            pipeline_factory=FakePipeline,
            sender=sender,
            summary_sender=summary_sender,
        )
        with self.assertLogs("app.worker", level="INFO") as captured:
            with (
                patch("app.worker.SessionLocal", self.session_factory),
                patch("app.matching.service.analyze_job_match", return_value=analysis),
            ):
                stats = await runner.run_profile(self.profile_id)

        db = self.session_factory()
        try:
            match = db.query(JobMatch).one()
            self.assertEqual(stats.discovered, 1)
            self.assertEqual(stats.matching_attempted, 1)
            self.assertEqual(stats.matched, 1)
            self.assertEqual(stats.rejected_by_match, 0)
            self.assertEqual(stats.notifications_attempted, 1)
            self.assertEqual(stats.notifications_sent, 1)
            self.assertEqual(stats.notifications_failed, 0)
            self.assertEqual(stats.notified, 1)
            self.assertTrue(match.notified)
            sender.assert_awaited_once()
            self.assertEqual(sender.await_args.args[0], 123)
            summary_sender.assert_awaited_once()
            self.assertEqual(summary_sender.await_args.args[0], "123")
            summary_message = summary_sender.await_args.args[1]
            self.assertIn("JOB SEARCH SUMMARY", summary_message)
            self.assertIn("Discovered: 1", summary_message)
            self.assertIn("Matched: 1", summary_message)
            self.assertIn("Notifications sent: 1", summary_message)
            audit_line = next(
                line for line in captured.output if "JOB_PIPELINE_AUDIT" in line
            )
            audit = json.loads(audit_line.split("JOB_PIPELINE_AUDIT ", 1)[1])
            self.assertTrue(audit["match"]["match_attempted"])
            self.assertEqual(audit["match"]["match_score"], 82.5)
            self.assertTrue(audit["match"]["match_passed"])
            self.assertTrue(audit["notification"]["notification_eligible"])
            self.assertTrue(audit["notification"]["telegram_send_attempted"])
            self.assertTrue(audit["notification"]["telegram_send_success"])
        finally:
            db.close()

    async def test_below_threshold_job_is_matched_but_not_notified(self) -> None:
        sender = AsyncMock()
        summary_sender = AsyncMock()
        analysis = JobMatchAnalysis(
            overall_score=74.9,
            skills_score=75,
            experience_score=70,
            title_score=80,
            education_score=75,
            location_score=100,
            matched_skills=["Python"],
            missing_skills=["AWS"],
            explanation="Below the configured threshold.",
        )
        runner = JobSearchRunner(
            pipeline_factory=FakePipeline,
            sender=sender,
            summary_sender=summary_sender,
        )
        with self.assertLogs("app.worker", level="INFO") as captured:
            with (
                patch("app.worker.SessionLocal", self.session_factory),
                patch("app.matching.service.analyze_job_match", return_value=analysis),
            ):
                stats = await runner.run_profile(self.profile_id)

        db = self.session_factory()
        try:
            match = db.query(JobMatch).one()
            self.assertEqual(match.score, 74.9)
            self.assertEqual(stats.matching_attempted, 1)
            self.assertEqual(stats.matched, 0)
            self.assertEqual(stats.rejected_by_match, 1)
            self.assertEqual(stats.notifications_attempted, 0)
            self.assertEqual(stats.notifications_sent, 0)
            self.assertFalse(match.notified)
            sender.assert_not_awaited()
            summary_sender.assert_awaited_once()
            self.assertEqual(summary_sender.await_args.args[0], "123")
            summary_message = summary_sender.await_args.args[1]
            self.assertIn("Matched: 0", summary_message)
            self.assertIn("Rejected by match: 1", summary_message)
            self.assertIn("Notifications sent: 0", summary_message)
            audit_line = next(
                line for line in captured.output if "JOB_PIPELINE_AUDIT" in line
            )
            audit = json.loads(audit_line.split("JOB_PIPELINE_AUDIT ", 1)[1])
            self.assertTrue(audit["match"]["match_attempted"])
            self.assertEqual(audit["match"]["match_score"], 74.9)
            self.assertFalse(audit["match"]["match_passed"])
            self.assertFalse(audit["notification"]["notification_eligible"])
            self.assertFalse(audit["notification"]["telegram_send_attempted"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
