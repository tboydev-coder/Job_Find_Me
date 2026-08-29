import os
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CandidateProfile, Job, JobMatch, UserProfile

from .schemas import JobMatchAnalysis
from .service import match_job


class MatchingPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.profile = UserProfile(name="Candidate", minimum_match=75)
        self.db.add(self.profile)
        self.db.commit()
        self.candidate = CandidateProfile(
            profile_id=self.profile.id,
            summary="Python backend engineer",
            skills="Python, FastAPI, PostgreSQL",
            job_titles="Backend Developer",
            experience="Three years building APIs",
            education="BSc Computer Science",
            keywords="APIs, SQL",
        )
        self.job = Job(
            source="test",
            title="Backend Engineer",
            company="Acme",
            location="Remote - Nigeria",
            description="Build APIs",
            requirements="Python and PostgreSQL",
            salary="$50,000",
            employment_type="FULL_TIME",
            apply_url="https://example.com/apply/1",
            content_hash="b" * 64,
        )
        self.db.add_all([self.candidate, self.job])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_candidate_loads_scores_save_and_threshold_applies(self) -> None:
        analysis = JobMatchAnalysis(
            overall_score=82.5,
            skills_score=85,
            experience_score=80,
            title_score=90,
            education_score=100,
            location_score=80,
            matched_skills=["Python", "PostgreSQL"],
            missing_skills=["AWS"],
            explanation="Strong backend alignment.",
        )
        with patch("app.matching.service.analyze_job_match", return_value=analysis) as mocked:
            candidate = self.db.query(CandidateProfile).filter_by(profile_id=self.profile.id).one()
            match, qualifies = match_job(
                self.db,
                self.profile.id,
                self.job,
                candidate,
                minimum_match=75,
            )
            duplicate, duplicate_qualifies = match_job(
                self.db,
                self.profile.id,
                self.job,
                candidate,
                minimum_match=85,
            )

        self.assertEqual(match.score, 82.5)
        self.assertTrue(qualifies)
        self.assertFalse(duplicate_qualifies)
        self.assertEqual(match.id, duplicate.id)
        self.assertEqual(self.db.query(JobMatch).count(), 1)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
