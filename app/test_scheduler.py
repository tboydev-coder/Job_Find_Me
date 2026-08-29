import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import UserProfile
from app.scheduler import ProfileScheduler


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        profile = UserProfile(search_enabled=True, search_interval_minutes=17)
        db.add(profile)
        db.commit()
        self.profile_id = profile.id
        db.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_profile_is_immediately_due_then_uses_its_interval(self) -> None:
        scheduler = ProfileScheduler(runner=object())
        with patch("app.scheduler.SessionLocal", self.session_factory):
            self.assertEqual(scheduler._due_profiles(), [self.profile_id])
            self.assertEqual(scheduler._due_profiles(), [])
            next_run = scheduler._next_runs[self.profile_id]
            remaining = next_run - datetime.now(timezone.utc)
            self.assertGreater(remaining, timedelta(minutes=16))


if __name__ == "__main__":
    unittest.main(verbosity=2)
