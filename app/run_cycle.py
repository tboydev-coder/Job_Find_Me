from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict

from app.database import SessionLocal
from app.models import UserProfile
from app.worker import CycleStats, JobSearchRunner


def _profile_ids(requested: list[int] | None) -> list[int]:
    if requested:
        return list(dict.fromkeys(requested))
    db = SessionLocal()
    try:
        return [
            profile_id
            for (profile_id,) in db.query(UserProfile.id)
            .filter(UserProfile.search_enabled.is_(True))
            .order_by(UserProfile.id)
            .all()
        ]
    finally:
        db.close()


async def run(profile_ids: list[int]) -> dict:
    runner = JobSearchRunner()
    totals = CycleStats()
    profile_results = {}
    for profile_id in profile_ids:
        stats = await runner.run_profile(profile_id, require_enabled=False)
        values = asdict(stats)
        profile_results[str(profile_id)] = values
        for field, value in values.items():
            setattr(totals, field, getattr(totals, field) + value)
    return {
        "profiles": profile_results,
        "totals": asdict(totals),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one complete Job-Find-Me cycle and print exact counters."
    )
    parser.add_argument(
        "--profile-id",
        action="append",
        type=int,
        help="Profile ID to run; repeat for multiple profiles. Defaults to all enabled profiles.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    results = asyncio.run(run(_profile_ids(args.profile_id)))
    print("PIPELINE_EXECUTION_RESULT " + json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
