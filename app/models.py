from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    """Return naive UTC for the existing TIMESTAMP WITHOUT TIME ZONE schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str | None] = mapped_column(
        String(100)
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    resume_text: Mapped[str | None] = mapped_column(
        Text
    )

    target_titles: Mapped[str | None] = mapped_column(
        Text
    )

    locations: Mapped[str | None] = mapped_column(
        Text
    )

    minimum_match: Mapped[int] = mapped_column(
        default=75
    )
    
    remote_preference: Mapped[str | None] = mapped_column(
        String(50)
    )

    search_enabled: Mapped[bool] = mapped_column(
        default=True
    )

    max_notifications_per_day: Mapped[int] = mapped_column(
        default=50
    )
    
    max_job_age_hours: Mapped[int] = mapped_column(
        Integer,
        default=24,
    )

    search_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
    )


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    profile_id: Mapped[int] = mapped_column(
        index=True
    )

    filename: Mapped[str] = mapped_column(
        String(255)
    )

    file_path: Mapped[str] = mapped_column(
        String(500)
    )

    extracted_text: Mapped[str | None] = mapped_column(
        Text
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow
    )
    
class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id"),
        unique=True,
        index=True,
    )

    summary: Mapped[str | None] = mapped_column(
        Text
    )

    skills: Mapped[str | None] = mapped_column(
        Text
    )

    job_titles: Mapped[str | None] = mapped_column(
        Text
    )

    experience: Mapped[str | None] = mapped_column(
        Text
    )

    education: Mapped[str | None] = mapped_column(
        Text
    )

    keywords: Mapped[str | None] = mapped_column(
        Text
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    source: Mapped[str] = mapped_column(
        String(100),
        index=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        index=True,
    )

    company: Mapped[str | None] = mapped_column(
        String(300),
        index=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(500),
    )

    description: Mapped[str | None] = mapped_column(
        Text,
    )

    requirements: Mapped[str | None] = mapped_column(
        Text,
    )

    salary: Mapped[str | None] = mapped_column(
        String(300),
    )

    employment_type: Mapped[str | None] = mapped_column(
        String(100),
    )

    apply_url: Mapped[str] = mapped_column(
        String(1000),
    )

    source_url: Mapped[str | None] = mapped_column(
        String(1000),
    )

    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        index=True,
    )

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )
    
class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "job_id",
            name="uq_job_matches_profile_job",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    profile_id: Mapped[int] = mapped_column(
        ForeignKey("user_profiles.id"),
        index=True,
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"),
        index=True,
    )

    score: Mapped[float] = mapped_column(
        Float,
    )

    skills_score: Mapped[float] = mapped_column(
        Float,
    )

    experience_score: Mapped[float] = mapped_column(
        Float,
    )

    title_score: Mapped[float] = mapped_column(
        Float,
    )

    education_score: Mapped[float] = mapped_column(
        Float,
    )

    location_score: Mapped[float] = mapped_column(
        Float,
    )

    matched_skills: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    missing_skills: Mapped[list] = mapped_column(
        JSON,
        default=list,
    )

    explanation: Mapped[str | None] = mapped_column(
        Text,
    )

    notified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
    )
