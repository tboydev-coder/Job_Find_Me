import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.config import Settings

from .groq_client import get_groq_client


logger = logging.getLogger(__name__)


class ExperienceItem(BaseModel):
    job_title: str
    company: str
    duration: str
    responsibilities: list[str]


class EducationItem(BaseModel):
    qualification: str
    institution: str
    field: str | None


class CandidateProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str

    skills: list[str]

    job_titles: list[str]

    experience: list[ExperienceItem]

    education: list[EducationItem]

    keywords: list[str]

def analyze_resume(
    resume_text: str,
    *,
    groq_client: Any | None = None,
    max_attempts: int = 2,
) -> CandidateProfileResponse:
    if not resume_text.strip():
        raise ValueError("Resume text is empty")

    client = groq_client or get_groq_client()
    model = Settings.from_environment().groq_model
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,

        messages=[
            {
                "role": "system",
                "content": """
You are a professional resume analysis system.

Analyze the candidate's resume and extract factual,
job-relevant information.

Do not invent experience, skills, qualifications,
companies, or education that are not present.

Return the information according to the provided
JSON schema.
""",
            },
            {
                "role": "user",
                "content": f"""
Analyze this resume:

--- RESUME START ---

{resume_text}

--- RESUME END ---
""",
            },
        ],

        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "candidate_profile",
                "strict": True,
                "schema": {
                    "type": "object",

                    "properties": {
                        "summary": {
                            "type": "string"
                        },

                        "skills": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        },

                        "job_titles": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        },

                        "experience": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "job_title": {
                                        "type": "string"
                                    },
                                    "company": {
                                        "type": "string"
                                    },
                                    "duration": {
                                        "type": "string"
                                    },
                                    "responsibilities": {
                                        "type": "array",
                                        "items": {
                                            "type": "string"
                                        }
                                    },
                                },
                                "required": [
                                    "job_title",
                                    "company",
                                    "duration",
                                    "responsibilities",
                                ],
                                "additionalProperties": False,
                            },
                        },

                        "education": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "qualification": {
                                        "type": "string"
                                    },
                                    "institution": {
                                        "type": "string"
                                    },
                                    "field": {
                                        "type": [
                                            "string",
                                            "null",
                                        ]
                                    },
                                },
                                "required": [
                                    "qualification",
                                    "institution",
                                    "field",
                                ],
                                "additionalProperties": False,
                            },
                        },

                        "keywords": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        },
                    },

                    "required": [
                        "summary",
                        "skills",
                        "job_titles",
                        "experience",
                        "education",
                        "keywords",
                    ],

                    "additionalProperties": False,
                },
            },
        },
    )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Groq returned an empty resume analysis")

            data = json.loads(content)
            return CandidateProfileResponse.model_validate(data)
        except Exception as error:
            last_error = error
            logger.warning(
                "Invalid Groq resume response (attempt %s/%s): %s",
                attempt,
                max_attempts,
                error,
            )

    raise RuntimeError("Groq returned an invalid resume analysis") from last_error
