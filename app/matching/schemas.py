from pydantic import BaseModel, ConfigDict, Field


class JobMatchAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: float = Field(ge=0, le=100)

    matched_skills: list[str]

    missing_skills: list[str]

    skills_score: float = Field(ge=0, le=100)

    experience_score: float = Field(ge=0, le=100)

    title_score: float = Field(ge=0, le=100)

    education_score: float = Field(ge=0, le=100)

    location_score: float = Field(ge=0, le=100)

    explanation: str
