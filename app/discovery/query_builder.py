def build_job_queries(
    target_titles: str,
    locations: str | None = None,
    remote_preference: str | None = None,
    max_job_age_hours: int | None = None,
) -> list[str]:

    titles = [
        title.strip()
        for title in target_titles.split(",")
        if title.strip()
    ]

    location_values = []

    if locations:
        location_values = [
            location.strip()
            for location in locations.split(",")
            if location.strip()
        ]

    queries = []

    recency_phrase = _recency_phrase(max_job_age_hours)

    job_sites = [
        "boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com",
        "apply.workable.com",
        "jobs.smartrecruiters.com",
    ]

    for title in titles:

        for site in job_sites:

            queries.append(
                f'"{title}" jobs {recency_phrase} site:{site}'.replace("  ", " ")
            )

        if location_values:

            for location in location_values:

                queries.append(
                    f'"{title}" "{location}" jobs {recency_phrase}'.strip()
                )

        if remote_preference or any(
            location.lower() == "remote"
            for location in location_values
        ):

            remote = (remote_preference or "remote").lower()

            if remote in {
                "remote",
                "preferred",
                "yes",
                "required",
            }:

                queries.append(
                    f'"{title}" remote jobs {recency_phrase}'.strip()
                )

    return list(
        dict.fromkeys(queries)
    )


def _recency_phrase(max_job_age_hours: int | None) -> str:
    if max_job_age_hours is None:
        return ""
    if max_job_age_hours <= 24:
        return "posted today"
    if max_job_age_hours <= 24 * 7:
        return "posted this week"
    if max_job_age_hours <= 24 * 31:
        return "posted this month"
    return "posted recently"
