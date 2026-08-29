from app.database import SessionLocal
from app.models import Job


def main():

    db = SessionLocal()

    try:
        jobs = (
            db.query(Job)
            .order_by(
                Job.created_at.desc()
            )
            .all()
        )

        print(
            f"\nJobs in database: {len(jobs)}"
        )

        for job in jobs:

            print("\n" + "=" * 60)

            print(
                f"ID: {job.id}"
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
                f"Posted: {job.posted_at}"
            )

            print(
                f"Apply URL: {job.apply_url}"
            )

    finally:

        db.close()


if __name__ == "__main__":
    main()