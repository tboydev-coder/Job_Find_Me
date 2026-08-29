import os
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
        analysis = JobMatchAnalysis(
            overall_score=88,
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
        )
        with (
            patch("app.worker.SessionLocal", self.session_factory),
            patch("app.matching.service.analyze_job_match", return_value=analysis),
        ):
            stats = await runner.run_profile(self.profile_id)

        db = self.session_factory()
        try:
            match = db.query(JobMatch).one()
            self.assertEqual(stats.discovered, 1)
            self.assertEqual(stats.matched, 1)
            self.assertEqual(stats.notified, 1)
            self.assertTrue(match.notified)
            sender.assert_awaited_once()
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
