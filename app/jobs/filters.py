from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from app.models import Job, UserProfile


ROLE_TERMS = {
    "administrator",
    "analyst",
    "architect",
    "consultant",
    "engineer",
    "scientist",
    "specialist",
}

GENERIC_TITLE_TERMS = ROLE_TERMS | {
    "associate",
    "intern",
    "job",
    "junior",
    "lead",
    "manager",
    "principal",
    "role",
    "senior",
    "software",
    "staff",
}

TITLE_REPLACEMENTS = {
    "back end": "backend",
    "front end": "frontend",
    "full stack": "fullstack",
    "machine learning": "machinelearning",
    "quality assurance": "qa",
    "server side": "backend",
}

TOKEN_SYNONYMS = {
    "coder": "engineer",
    "developer": "engineer",
    "development": "engineer",
    "programmer": "engineer",
}

REMOTE_MARKERS = {
    "distributed",
    "remote",
    "telecommute",
    "work from home",
}

GLOBAL_MARKERS = {
    "any location",
    "anywhere",
    "global",
    "worldwide",
}

KNOWN_COUNTRIES = {
    "argentina",
    "australia",
    "brazil",
    "canada",
    "france",
    "germany",
    "ghana",
    "india",
    "ireland",
    "kenya",
    "mexico",
    "netherlands",
    "nigeria",
    "paraguay",
    "portugal",
    "south africa",
    "spain",
    "united kingdom",
    "united states",
    "uk",
    "usa",
}

AFRICAN_COUNTRIES = {
    "algeria",
    "angola",
    "cameroon",
    "egypt",
    "ethiopia",
    "ghana",
    "kenya",
    "morocco",
    "nigeria",
    "rwanda",
    "south africa",
    "tanzania",
    "uganda",
    "zambia",
    "zimbabwe",
}

CITY_COUNTRY = {
    "abuja": "nigeria",
    "lagos": "nigeria",
}

INVALID_LOCATIONS = {
    "*",
    "google maps requires functional cookies to be enabled",
    "location",
    "not specified",
    "status full time",
}


def is_recent(
    job: Job,
    profile: UserProfile,
    *,
    now: datetime | None = None,
) -> bool:
    """Unknown dates are ineligible; the service never invents freshness."""
    if not job.posted_at:
        return False

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    posted_at = job.posted_at
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    else:
        posted_at = posted_at.astimezone(timezone.utc)

    age = current - posted_at
    if age < -timedelta(hours=1):
        return False
    maximum_age = timedelta(hours=max(0, profile.max_job_age_hours))
    return age <= maximum_age


def title_matches(job: Job, profile: UserProfile) -> bool:
    if not job.title:
        return False
    if not profile.target_titles:
        return True

    job_normalized, job_tokens = _normalize_title(job.title)
    job_roles = job_tokens & ROLE_TERMS
    if not job_roles:
        return False

    targets = _split_csv(profile.target_titles)
    for target in targets:
        target_normalized, target_tokens = _normalize_title(target)
        if target_normalized and target_normalized in job_normalized:
            return True

        target_roles = target_tokens & ROLE_TERMS
        if not target_roles:
            continue
        specific_terms = target_tokens - GENERIC_TITLE_TERMS
        if specific_terms:
            overlap = specific_terms & job_tokens
            if overlap and len(overlap) / len(specific_terms) >= 0.5:
                return True
        elif target_roles & job_roles:
            return True
    return False


def location_matches(job: Job, profile: UserProfile) -> bool:
    if not profile.locations:
        return True
    if not job.location:
        return False

    job_location = _normalize_text(job.location)
    if not job_location or job_location in INVALID_LOCATIONS:
        return False

    configured = [_normalize_text(value) for value in _split_csv(profile.locations)]
    configured = [value for value in configured if value]
    requested_remote = any(_is_remote(value) for value in configured)
    requested_geo = [value for value in configured if not _is_remote(value)]
    preference = _normalize_text(profile.remote_preference or "")
    remote_required = preference in {"remote", "required", "remote only", "yes"}
    remote_forbidden = preference in {"no", "onsite", "on site", "office"}

    job_is_remote = _is_remote(job_location)
    if not job_is_remote:
        if remote_required:
            return False
        return any(_location_overlap(job_location, location) for location in requested_geo)

    if remote_forbidden:
        return False

    # Worldwide remote is compatible with every configured geography.
    if any(marker in job_location for marker in GLOBAL_MARKERS):
        return True

    scopes = _country_scopes(job_location)
    if "africa" in job_location:
        return any(_configured_country(value) in AFRICAN_COUNTRIES for value in requested_geo)
    if scopes:
        return any(_configured_country(value) in scopes for value in requested_geo)

    # A plain "Remote" posting has no contradictory geographic restriction.
    return requested_remote or remote_required or bool(requested_geo)


def job_matches_profile(job: Job, profile: UserProfile) -> bool:
    return (
        is_recent(job, profile)
        and title_matches(job, profile)
        and location_matches(job, profile)
    )


def rejection_reason(job: Job, profile: UserProfile) -> str:
    if not is_recent(job, profile):
        return "posting date is missing, invalid, or too old"
    if not title_matches(job, profile):
        return "title does not match"
    if not location_matches(job, profile):
        return "location does not match"
    return "accepted"


def _normalize_title(value: str) -> tuple[str, set[str]]:
    normalized = _normalize_text(value)
    for original, replacement in TITLE_REPLACEMENTS.items():
        normalized = re.sub(rf"\b{re.escape(original)}\b", replacement, normalized)
    tokens = {
        TOKEN_SYNONYMS.get(token, token)
        for token in normalized.split()
        if token
    }
    return " ".join(TOKEN_SYNONYMS.get(token, token) for token in normalized.split()), tokens


def _normalize_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _is_remote(value: str) -> bool:
    return any(marker in value for marker in REMOTE_MARKERS)


def _country_scopes(value: str) -> set[str]:
    return {country for country in KNOWN_COUNTRIES if _contains_phrase(value, country)}


def _configured_country(value: str) -> str:
    scopes = _country_scopes(value)
    if scopes:
        return next(iter(scopes))
    for city, country in CITY_COUNTRY.items():
        if _contains_phrase(value, city):
            return country
    return value


def _location_overlap(job_location: str, configured: str) -> bool:
    if _contains_phrase(job_location, configured):
        return True
    configured_country = _configured_country(configured)
    return configured_country != configured and _contains_phrase(job_location, configured_country)


def _contains_phrase(value: str, phrase: str) -> bool:
    return bool(re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", value))
