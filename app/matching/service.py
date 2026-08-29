from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .filter import meets_minimum_match
from app.models import (
    CandidateProfile,
    Job,
    JobMatch,
)

from .matcher import (
    analyze_job_match,
    calculate_match_score,
)


def match_job(
    db: Session,
    profile_id: int,
    job: Job,
    candidate_profile: CandidateProfile,
    minimum_match: int,
) -> tuple[JobMatch, bool]:

    existing = (
        db.query(JobMatch)
        .filter(
            JobMatch.profile_id == profile_id,
            JobMatch.job_id == job.id,
        )
        .first()
    )
    if existing:
        return (
            existing,
            meets_minimum_match(existing.score, minimum_match),
        )

    candidate_data = {
        "summary": candidate_profile.summary,
        "skills": candidate_profile.skills,
        "job_titles": candidate_profile.job_titles,
        "experience": candidate_profile.experience,
        "education": candidate_profile.education,
        "keywords": candidate_profile.keywords,
    }

    job_data = {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
        "employment_type": job.employment_type,
        "salary": job.salary,
    }

    analysis = analyze_job_match(
        candidate_profile=candidate_data,
        job=job_data,
    )

    score = calculate_match_score(
        analysis
    )
    
    meets_threshold = meets_minimum_match(
        score=score,
        minimum_match=minimum_match,
    )

    match = JobMatch(
        profile_id=profile_id,
        job_id=job.id,

        score=score,

        skills_score=(
            analysis.skills_score
        ),

        experience_score=(
            analysis.experience_score
        ),

        title_score=(
            analysis.title_score
        ),

        education_score=(
            analysis.education_score
        ),

        location_score=(
            analysis.location_score
        ),

        matched_skills=(
            analysis.matched_skills
        ),

        missing_skills=(
            analysis.missing_skills
        ),

        explanation=(
            analysis.explanation
        ),

        notified=False,
    )

    db.add(match)

    try:
        db.commit()
        db.refresh(match)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(JobMatch)
            .filter(
                JobMatch.profile_id == profile_id,
                JobMatch.job_id == job.id,
            )
            .one()
        )
        return (
            existing,
            meets_minimum_match(existing.score, minimum_match),
        )

    return match, meets_threshold
