from app.database import SessionLocal
from app.models import UserProfile, CandidateProfile


def main():

    db = SessionLocal()

    try:

        profile = (
            db.query(UserProfile)
            .first()
        )

        if not profile:
            print("No UserProfile found.")
            return

        print(
            f"Using UserProfile: "
            f"{profile.name} "
            f"(ID: {profile.id})"
        )

        existing = (
            db.query(CandidateProfile)
            .filter(
                CandidateProfile.profile_id
                == profile.id
            )
            .first()
        )

        if existing:
            print(
                "CandidateProfile already exists."
            )
            print(
                f"CandidateProfile ID: "
                f"{existing.id}"
            )
            return

        candidate = CandidateProfile(

            profile_id=profile.id,

            summary=(
                "Backend developer with "
                "experience building APIs and "
                "backend applications."
            ),

            skills=(
                "Python, FastAPI, PostgreSQL, "
                "REST APIs, SQL, Git"
            ),

            job_titles=(
                "Backend Developer, "
                "Python Developer"
            ),

            experience=(
                "2 years of backend development "
                "experience."
            ),

            education=(
                "Bachelor's degree in Computer Science"
            ),

            keywords=(
                "Python, FastAPI, PostgreSQL, "
                "REST API, backend, SQL"
            ),
        )

        db.add(candidate)

        db.commit()

        db.refresh(candidate)

        print()
        print("=" * 50)
        print("CANDIDATE PROFILE CREATED")
        print("=" * 50)
        print(
            f"CandidateProfile ID: "
            f"{candidate.id}"
        )
        print(
            f"UserProfile ID: "
            f"{candidate.profile_id}"
        )
        print("=" * 50)

    finally:

        db.close()


if __name__ == "__main__":
    main()