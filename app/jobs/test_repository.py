import os
import unittest


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base

from .repository import normalize_job_url, save_or_get_job
from .schemas import JobData


class JobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_tracking_parameters_do_not_create_duplicates(self) -> None:
        first = JobData(
            source="jobs.example.com",
            title="Backend Engineer",
            company="Acme",
            apply_url="https://jobs.example.com/42?utm_source=tavily&ref=search",
        )
        second = first.model_copy(
            update={"apply_url": "https://jobs.example.com/42?utm_campaign=jobs"}
        )
        saved, created = save_or_get_job(self.db, first)
        duplicate, duplicate_created = save_or_get_job(self.db, second)
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(saved.id, duplicate.id)
        self.assertEqual(saved.apply_url, "https://jobs.example.com/42")

    def test_url_normalization_keeps_non_tracking_parameters(self) -> None:
        normalized = normalize_job_url(
            "HTTPS://Example.COM/jobs/42/?department=eng&utm_medium=search#apply"
        )
        self.assertEqual(normalized, "https://example.com/jobs/42?department=eng")


if __name__ == "__main__":
    unittest.main(verbosity=2)
