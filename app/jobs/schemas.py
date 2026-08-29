from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=100)

    external_id: str | None = Field(default=None, max_length=255)

    title: str = Field(min_length=2, max_length=500)

    company: str | None = Field(default=None, max_length=300)

    location: str | None = Field(default=None, max_length=500)

    description: str | None = None

    requirements: str | None = None

    salary: str | None = Field(default=None, max_length=300)

    employment_type: str | None = Field(default=None, max_length=100)

    apply_url: str = Field(min_length=8, max_length=1000)

    source_url: str | None = Field(default=None, max_length=1000)

    posted_at: datetime | None = None

    @field_validator("apply_url", "source_url")
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().startswith(("http://", "https://")):
            raise ValueError("job URLs must use HTTP or HTTPS")
        return value
