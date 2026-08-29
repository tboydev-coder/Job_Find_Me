import json
import logging
from typing import Any

from app.ai.groq_client import get_groq_client
from app.config import Settings
from app.logging_utils import safe_exception_text, safe_response_excerpt

from .schemas import JobMatchAnalysis


logger = logging.getLogger(__name__)


def analyze_job_match(
    candidate_profile: dict,
    job: dict,
    *,
    groq_client: Any | None = None,
    max_attempts: int = 2,
) -> JobMatchAnalysis:

    prompt = f"""
You are a professional job-matching system.

Your job is to evaluate how well a candidate matches
a specific job.

CANDIDATE PROFILE:

{json.dumps(
    candidate_profile,
    indent=2,
)}

JOB:

{json.dumps(
    job,
    indent=2,
)}

Evaluate the candidate against the job.

IMPORTANT RULES:

1. Do not invent skills, experience, education, certifications, or
   qualifications. Score only evidence in the candidate profile.

2. Only consider information that actually exists
   in the candidate profile, and ones that are relevant that the candidate should possess but are left out.

3. Identify the skills that match the job.

4. Identify important skills required by the job
   that are missing from the candidate profile.

5. Evaluate the candidate's relevant experience.

6. Evaluate how closely the candidate's job titles
   align with the job title.

7. Evaluate education only when it is relevant
   to the job.

8. Evaluate location compatibility.

9. Every score must be between 0 and 100.

10. Calculate overall_score conservatively from the component scores.

11. Keep the explanation concise and practical.

Return your analysis using the required JSON structure.
"""

    client = groq_client or get_groq_client()
    model = Settings.from_environment().groq_model
    last_error: Exception | None = None
    last_content: object = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,

        messages=[
            {
                "role": "system",
                "content": (
                    "You are an accurate and "
                    "conservative job matching "
                    "system."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],

        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "job_match_analysis",

                "strict": True,

                "schema": {
                    "type": "object",

                    "properties": {
                        "overall_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "matched_skills": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                        },

                        "missing_skills": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                        },

                        "skills_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },

                        "experience_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },

                        "title_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },

                        "education_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },

                        "location_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                        },

                        "explanation": {
                            "type": "string",
                        },
                    },

                    "required": [
                        "overall_score",
                        "matched_skills",
                        "missing_skills",
                        "skills_score",
                        "experience_score",
                        "title_score",
                        "education_score",
                        "location_score",
                        "explanation",
                    ],

                    "additionalProperties": False,
                },
            },
        },
    )

            content = response.choices[0].message.content
            last_content = content
            if not content:
                raise ValueError("Groq returned an empty match response")

            data = json.loads(content)
            return JobMatchAnalysis.model_validate(data)
        except Exception as error:
            last_error = error
            logger.warning(
                "MATCH_MODEL_ERROR %s",
                json.dumps(
                    {
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error": safe_exception_text(error),
                        "response_excerpt": safe_response_excerpt(last_content),
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )

    raise RuntimeError(
        "Groq returned an invalid job match response after "
        f"{max_attempts} attempt(s): {safe_exception_text(last_error)}"
    ) from last_error


def calculate_match_score(
    analysis: JobMatchAnalysis,
) -> float:

    return round(analysis.overall_score, 2)
