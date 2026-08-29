import asyncio

from dotenv import load_dotenv

from app.database import SessionLocal

from .pipeline import (
    JobDiscoveryPipeline,
)


async def main():

    load_dotenv()

    db = SessionLocal()

    try:

        pipeline = (
            JobDiscoveryPipeline()
        )

        jobs = (
            await pipeline.search_and_save(
                db=db,
                query='"Python Developer" Lagos jobs',
                limit=5,
            )
        )

        print(
            f"\nSaved {len(jobs)} new jobs."
        )

        for job in jobs:

            print("\n" + "=" * 60)

            print(
                "TITLE:",
                job.title,
            )

            print(
                "COMPANY:",
                job.company,
            )

            print(
                "LOCATION:",
                job.location,
            )

            print(
                "POSTED:",
                job.posted_at,
            )

            print(
                "APPLY:",
                job.apply_url,
            )

    finally:

        db.close()


if __name__ == "__main__":
    asyncio.run(main())