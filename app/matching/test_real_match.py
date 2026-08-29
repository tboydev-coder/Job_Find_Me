from app.database import SessionLocal

from app.models import (
    UserProfile,
    CandidateProfile,
    Job,
)

from .service import match_job


def main():

    db = SessionLocal()

    try:

        profile = (
            db.query(UserProfile)
            .filter(
                UserProfile.telegram_chat_id.isnot(None)
            )
            .first()
        )

        if not profile:

            print(
                "No UserProfile found."
            )

            return

        candidate_profile = (
            db.query(CandidateProfile)
            .filter(
                CandidateProfile.profile_id
                == profile.id
            )
            .first()
        )

        if not candidate_profile:

            print(
                "No CandidateProfile found "
                f"for profile {profile.id}."
            )

            return

        job = (
            db.query(Job)
            .order_by(
                Job.created_at.desc()
            )
            .first()
        )

        if not job:

            print(
                "No jobs found in database."
            )

            return

        print(
            "\nCandidate:"
        )

        print(
            candidate_profile.summary
        )

        print(
            "\nJob:"
        )

        print(
            job.title
        )

        print(
            job.company
        )

        print(
            "\nRunning AI match..."
        )

        match, meets_threshold = match_job(
            db=db,

            profile_id=profile.id,

            job=job,

            candidate_profile=(
                candidate_profile
            ),

            minimum_match=(
                profile.minimum_match
            ),
        )

        print(
            "\nMATCH CREATED"
        )

        print(
            "=" * 50
        )

        print(
            f"Match ID: {match.id}"
        )

        print(
            f"Job ID: {match.job_id}"
        )

        print(
            f"Match Score: {match.score}%"
        )
        
        print(
            f"Minimum Required: "
            f"{profile.minimum_match}%"
        )

        print(
            f"Passed Threshold: "
            f"{'YES' if meets_threshold else 'NO'}"
        )

        print(
            "\nMatched Skills:"
        )

        for skill in (
            match.matched_skills or []
        ):

            print(
                f"  ✓ {skill}"
            )

        print(
            "\nMissing Skills:"
        )

        for skill in (
            match.missing_skills or []
        ):

            print(
                f"  ✗ {skill}"
            )

        print(
            "\nExplanation:"
        )

        print(
            match.explanation
        )

    finally:

        db.close()


if __name__ == "__main__":
    main()