import os
import unittest
from datetime import datetime, timedelta, timezone


os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.models import Job, UserProfile

from .filters import is_recent, location_matches, title_matches


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def make_profile(**overrides) -> UserProfile:
    values = {
        "target_titles": "Backend Developer, Python Developer",
        "locations": "Nigeria, Remote",
        "remote_preference": "preferred",
        "max_job_age_hours": 24,
    }
    values.update(overrides)
    return UserProfile(**values)


def make_job(**overrides) -> Job:
    values = {
        "source": "test",
        "title": "Backend Engineer",
        "location": "Lagos, Nigeria",
        "apply_url": "https://example.com/apply/1",
        "content_hash": "a" * 64,
        "posted_at": NOW - timedelta(hours=6),
    }
    values.update(overrides)
    return Job(**values)


class JobFilterTests(unittest.TestCase):
    def test_related_backend_titles_match(self) -> None:
        profile = make_profile(target_titles="Backend Developer")
        titles = [
            "Backend Engineer",
            "Senior Backend Developer",
            "Python Backend Developer",
            "Backend Software Engineer",
            "Software Engineer - Backend",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertTrue(title_matches(make_job(title=title), profile))

    def test_unrelated_titles_do_not_match(self) -> None:
        profile = make_profile(target_titles="Backend Developer")
        for title in ("Frontend Developer", "Graphic Designer", "Marketing Manager"):
            with self.subTest(title=title):
                self.assertFalse(title_matches(make_job(title=title), profile))

    def test_locations_and_remote_scope(self) -> None:
        profile = make_profile()
        accepted = (
            "Lagos, Nigeria",
            "Remote",
            "Remote - Nigeria",
            "Remote - Africa",
            "Worldwide Remote",
        )
        for location in accepted:
            with self.subTest(location=location):
                self.assertTrue(location_matches(make_job(location=location), profile))
        self.assertFalse(location_matches(make_job(location="Remote - Paraguay"), profile))
        self.assertFalse(location_matches(make_job(location=None), profile))

    def test_remote_required_rejects_onsite(self) -> None:
        profile = make_profile(remote_preference="required")
        self.assertFalse(location_matches(make_job(location="Lagos, Nigeria"), profile))

    def test_recent_old_boundary_and_missing_dates(self) -> None:
        profile = make_profile(max_job_age_hours=24)
        self.assertTrue(is_recent(make_job(posted_at=NOW - timedelta(hours=24)), profile, now=NOW))
        self.assertFalse(
            is_recent(make_job(posted_at=NOW - timedelta(hours=24, seconds=1)), profile, now=NOW)
        )
        self.assertFalse(is_recent(make_job(posted_at=None), profile, now=NOW))


if __name__ == "__main__":
    unittest.main(verbosity=2)
