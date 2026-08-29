def build_job_queries(
    target_titles: str,
    locations: str | None = None,
    remote_preference: str | None = None,
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
                f'"{title}" jobs site:{site}'
            )

        if location_values:

            for location in location_values:

                queries.append(
                    f'"{title}" "{location}" jobs'
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
                    f'"{title}" remote jobs'
                )

    return list(
        dict.fromkeys(queries)
    )
