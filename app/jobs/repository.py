import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job

from .schemas import JobData


def create_job_hash(job: JobData) -> str:
    normalized_url = normalize_job_url(job.apply_url)
    if job.external_id:
        raw = f"{job.source}|{job.external_id}".lower().strip()
    else:
        raw = (
            f"{job.title}|{job.company or ''}|{normalized_url}"
        ).lower().strip()

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def job_exists(
    db: Session,
    content_hash: str,
) -> bool:

    return (
        db.query(Job)
        .filter(
            Job.content_hash == content_hash
        )
        .first()
        is not None
    )


def normalize_job_url(url: str) -> str:
    """Remove fragments and common tracking parameters from job URLs."""
    parsed = urlsplit(url.strip())
    tracking_names = {
        "fbclid",
        "gclid",
        "ref",
        "referrer",
        "source",
    }
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in tracking_names
    ]
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def find_existing_job(db: Session, job_data: JobData) -> Job | None:
    content_hash = create_job_hash(job_data)
    existing = db.query(Job).filter(Job.content_hash == content_hash).first()
    if existing:
        return existing
    if job_data.external_id:
        return (
            db.query(Job)
            .filter(
                Job.source == job_data.source,
                Job.external_id == job_data.external_id,
            )
            .first()
        )
    return None


def save_or_get_job(db: Session, job_data: JobData) -> tuple[Job, bool]:
    existing = find_existing_job(db, job_data)
    if existing:
        return existing, False

    normalized_apply_url = normalize_job_url(job_data.apply_url)
    normalized_source_url = (
        normalize_job_url(job_data.source_url) if job_data.source_url else None
    )
    job = Job(
        source=job_data.source,
        external_id=job_data.external_id,
        title=job_data.title,
        company=job_data.company,
        location=job_data.location,
        description=job_data.description,
        requirements=job_data.requirements,
        salary=job_data.salary,
        employment_type=job_data.employment_type,
        apply_url=normalized_apply_url,
        source_url=normalized_source_url,
        posted_at=job_data.posted_at,
        content_hash=create_job_hash(job_data),
    )
    db.add(job)
    try:
        db.commit()
        db.refresh(job)
        return job, True
    except IntegrityError:
        db.rollback()
        existing = find_existing_job(db, job_data)
        if existing is None:
            raise
        return existing, False


def save_job(
    db: Session,
    job_data: JobData,
) -> Job | None:

    job, created = save_or_get_job(db, job_data)
    return job if created else None
