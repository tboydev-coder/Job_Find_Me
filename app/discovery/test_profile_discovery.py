import asyncio

from app.database import SessionLocal
from app.models import UserProfile

from .pipeline import JobDiscoveryPipeline


async def main():

    db = SessionLocal()

    try:

        profile = (
            db.query(UserProfile)
            .filter(
                UserProfile.search_enabled == True
            )
            .first()
        )

        if not profile:

            print(
                "No enabled UserProfile found."
            )

            return

        if not profile.target_titles:

            print(
                "UserProfile has no target titles."
            )

            return

        print(
            "\nPROFILE"
        )

        print(
            "=" * 60
        )

        print(
            "Target titles:",
            profile.target_titles,
        )

        print(
            "Locations:",
            profile.locations,
        )

        print(
            "Remote preference:",
            profile.remote_preference,
        )

        pipeline = JobDiscoveryPipeline()

        jobs = await pipeline.search_profile(
            db=db,

            target_titles=(
                profile.target_titles
            ),

            locations=(
                profile.locations
            ),

            remote_preference=(
                profile.remote_preference
            ),

            limit_per_query=5,
        )

        print(
            "\n" + "=" * 60
        )

        print(
            "DISCOVERY COMPLETE"
        )

        print(
            "=" * 60
        )

        print(
            f"New jobs saved: {len(jobs)}"
        )

        for job in jobs:

            print(
                "\n" + "-" * 60
            )

            print(
                f"Title: {job.title}"
            )

            print(
                f"Company: {job.company}"
            )

            print(
                f"Location: {job.location}"
            )

            print(
                f"Apply URL: {job.apply_url}"
            )

    finally:

        db.close()


if __name__ == "__main__":
    asyncio.run(main())