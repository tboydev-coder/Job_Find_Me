import json
import unittest
from types import SimpleNamespace

from .matcher import analyze_job_match, calculate_match_score


class FakeCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.contents = iter(contents)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        content = next(self.contents)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class MatcherTests(unittest.TestCase):
    def test_groq_json_is_strictly_parsed(self) -> None:
        payload = {
            "overall_score": 82.5,
            "matched_skills": ["Python"],
            "missing_skills": ["AWS"],
            "skills_score": 85,
            "experience_score": 80,
            "title_score": 90,
            "education_score": 100,
            "location_score": 80,
            "explanation": "Strong fit.",
        }
        completions = FakeCompletions([json.dumps(payload)])
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        analysis = analyze_job_match({}, {}, groq_client=client)
        self.assertEqual(calculate_match_score(analysis), 82.5)

    def test_malformed_response_is_retried(self) -> None:
        valid = {
            "overall_score": 75,
            "matched_skills": [],
            "missing_skills": [],
            "skills_score": 75,
            "experience_score": 75,
            "title_score": 75,
            "education_score": 75,
            "location_score": 75,
            "explanation": "Meets threshold.",
        }
        completions = FakeCompletions(["not json", json.dumps(valid)])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        analysis = analyze_job_match({}, {}, groq_client=client, max_attempts=2)
        self.assertEqual(analysis.overall_score, 75)
        self.assertEqual(completions.calls, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
