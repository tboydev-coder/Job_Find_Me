from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str

    external_id: str | None = None

    title: str = Field(min_length=2, max_length=500)

    company: str | None = None

    location: str | None = None

    description: str | None = None

    requirements: str | None = None

    salary: str | None = None

    employment_type: str | None = None

    apply_url: str = Field(min_length=8, max_length=1000)

    source_url: str | None = None

    posted_at: datetime | None = None

    @field_validator("apply_url", "source_url")
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().startswith(("http://", "https://")):
            raise ValueError("job URLs must use HTTP or HTTPS")
        return value
