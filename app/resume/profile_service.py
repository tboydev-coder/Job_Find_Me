from sqlalchemy.orm import Session

from app.models import CandidateProfile
from app.ai.resume_analyzer import CandidateProfileResponse


def save_candidate_profile(
    db: Session,
    profile_id: int,
    analysis: CandidateProfileResponse,
):
    existing = (
        db.query(CandidateProfile)
        .filter(
            CandidateProfile.profile_id == profile_id
        )
        .first()
    )

    skills = ", ".join(analysis.skills)
    job_titles = ", ".join(analysis.job_titles)
    keywords = ", ".join(analysis.keywords)

    experience = "\n".join(
        [
            (
                f"{item.job_title} at "
                f"{item.company} "
                f"({item.duration})\n"
                + "\n".join(
                    f"- {responsibility}"
                    for responsibility
                    in item.responsibilities
                )
            )
            for item in analysis.experience
        ]
    )

    education = "\n".join(
        [
            (
                f"{item.qualification} - "
                f"{item.institution}"
                + (
                    f" ({item.field})"
                    if item.field
                    else ""
                )
            )
            for item in analysis.education
        ]
    )

    if existing:
        existing.summary = analysis.summary
        existing.skills = skills
        existing.job_titles = job_titles
        existing.experience = experience
        existing.education = education
        existing.keywords = keywords

        db.commit()
        db.refresh(existing)

        return existing

    candidate = CandidateProfile(
        profile_id=profile_id,
        summary=analysis.summary,
        skills=skills,
        job_titles=job_titles,
        experience=experience,
        education=education,
        keywords=keywords,
    )

    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return candidate