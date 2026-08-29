import unittest

from .query_builder import build_job_queries


class QueryBuilderTests(unittest.TestCase):
    def test_multiple_titles_and_locations_generate_distinct_queries(self) -> None:
        queries = build_job_queries(
            target_titles="Python Developer, Backend Developer",
            locations="Nigeria, Remote",
            remote_preference="preferred",
        )
        self.assertIn('"Python Developer" "Nigeria" jobs', queries)
        self.assertIn('"Backend Developer" "Remote" jobs', queries)
        self.assertIn('"Python Developer" remote jobs', queries)
        self.assertEqual(len(queries), len(set(queries)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
