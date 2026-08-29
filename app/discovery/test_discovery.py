import unittest

from .extractor import (
    convert_job_posting,
    extract_fallback_job,
    extract_json_ld,
    find_job_posting,
)


class DiscoveryExtractionTests(unittest.TestCase):
    def test_valid_job_posting_is_accepted_and_extracted(self) -> None:
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "identifier": {"value": "BE-42"},
          "title": "Python Backend Engineer",
          "hiringOrganization": {"@type": "Organization", "name": "Acme"},
          "jobLocationType": "TELECOMMUTE",
          "applicantLocationRequirements": {"@type": "Country", "name": "Nigeria"},
          "datePosted": "2026-08-28T10:00:00Z",
          "description": "<p>Build Python services.</p>",
          "qualifications": "Python and PostgreSQL",
          "employmentType": ["FULL_TIME", "CONTRACTOR"],
          "url": "https://jobs.example.com/apply/42"
        }
        </script>
        """
        posting = find_job_posting(extract_json_ld(html))
        self.assertIsNotNone(posting)
        job = convert_job_posting(posting, "https://jobs.example.com/jobs/42")
        self.assertEqual(job.company, "Acme")
        self.assertEqual(job.location, "Remote - Nigeria")
        self.assertEqual(job.external_id, "BE-42")
        self.assertEqual(job.apply_url, "https://jobs.example.com/apply/42")
        self.assertIsNotNone(job.posted_at)

    def test_article_is_rejected(self) -> None:
        html = """
        <html><body><h1>How to Become a Python Developer</h1>
        <main>Complete guide and tutorial. Requirements, responsibilities,
        qualifications, full-time, benefits and apply now.</main>
        <a href="/newsletter/apply">Apply now</a></body></html>
        """
        job = extract_fallback_job(html, "https://example.com/blog/python-career")
        self.assertIsNone(job)

    def test_strong_ats_fallback_page_is_accepted(self) -> None:
        html = """
        <html><head>
        <meta name="company" content="Acme">
        <meta name="job:location" content="Lagos, Nigeria">
        <meta name="job:datePosted" content="2026-08-28T09:00:00Z">
        </head><body><h1>Backend Engineer</h1><main>
        Responsibilities: build APIs. Requirements: Python. Qualifications:
        PostgreSQL. This is a full-time role with benefits and three years of
        experience. Apply for this job below.
        </main><a href="/apply/42">Apply now</a></body></html>
        """
        job = extract_fallback_job(
            html,
            "https://jobs.lever.co/acme/backend-42",
        )
        self.assertIsNotNone(job)
        self.assertEqual(job.company, "Acme")
        self.assertEqual(job.location, "Lagos, Nigeria")
        self.assertEqual(job.apply_url, "https://jobs.lever.co/apply/42")
        self.assertIsNotNone(job.posted_at)

    def test_graph_job_posting_is_detected(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@graph": [{"@type": "WebPage"},
        {"@type": "JobPosting", "title": "Backend Engineer"}]}
        </script>
        """
        posting = find_job_posting(extract_json_ld(html))
        self.assertEqual(posting["title"], "Backend Engineer")

    def test_array_type_is_detected(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": ["Thing", "JobPosting"], "title": "API Engineer"}
        </script>
        """
        posting = find_job_posting(extract_json_ld(html))
        self.assertEqual(posting["title"], "API Engineer")

    def test_malformed_json_ld_does_not_crash(self) -> None:
        html = '<script type="application/ld+json">{"@type": JobPosting}</script>'
        self.assertEqual(extract_json_ld(html), [])
        self.assertIsNone(find_job_posting(extract_json_ld(html)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
