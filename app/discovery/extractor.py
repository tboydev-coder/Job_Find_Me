from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterator
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.jobs.schemas import JobData


logger = logging.getLogger(__name__)

BLOCKED_HOSTS = {
    "facebook.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
}

KNOWN_JOB_HOSTS = {
    "apply.workable.com",
    "boards.greenhouse.io",
    "careers.smartrecruiters.com",
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
}

NON_JOB_TITLE_PHRASES = {
    "career advice",
    "complete guide",
    "how to",
    "in demand skills",
    "interview questions",
    "job description",
    "salary guide",
    "tutorial",
}

NON_JOB_CONTENT_PHRASES = NON_JOB_TITLE_PHRASES - {"job description"}


class JobPageExtractor:
    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def fetch(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text


def clean_html(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = [clean_html(item) for item in value]
        return "\n".join(part for part in parts if part) or None
    if isinstance(value, dict):
        value = value.get("name") or value.get("value")
    if not isinstance(value, (str, int, float)):
        return None
    soup = BeautifulSoup(str(value), "lxml")
    text = soup.get_text("\n", strip=True)
    return text or None


def extract_json_ld(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        raw = re.sub(r"^\s*<!--|-->\s*$", "", raw.strip())
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.debug("Ignoring malformed JSON-LD script")
            continue
        if isinstance(data, dict):
            results.append(data)
        elif isinstance(data, list):
            results.extend(item for item in data if isinstance(item, dict))
    return results


def _walk_json(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _has_schema_type(value: Any, expected: str) -> bool:
    values = value if isinstance(value, list) else [value]
    return any(
        isinstance(item, str)
        and item.rstrip("/").rsplit("/", 1)[-1].lower() == expected.lower()
        for item in values
    )


def find_job_posting(
    structured_data: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for root in structured_data:
        for node in _walk_json(root):
            if _has_schema_type(node.get("@type"), "JobPosting"):
                return node
    return None


def convert_job_posting(posting: dict[str, Any], source_url: str) -> JobData:
    title = clean_html(posting.get("title") or posting.get("name"))
    if not title or _bad_title(title):
        raise ValueError("JobPosting has no credible title")

    company = extract_organization_name(posting.get("hiringOrganization"))
    location = extract_location(
        posting.get("jobLocation"),
        job_location_type=posting.get("jobLocationType"),
        applicant_requirements=posting.get("applicantLocationRequirements"),
    )
    requirements_values = [
        posting.get("qualifications"),
        posting.get("skills"),
        posting.get("experienceRequirements"),
        posting.get("educationRequirements"),
    ]
    requirements = clean_html([value for value in requirements_values if value])
    description = clean_html(
        posting.get("description") or posting.get("responsibilities")
    )

    apply_url = _absolute_http_url(posting.get("url"), source_url) or source_url
    if not _absolute_http_url(apply_url, source_url):
        raise ValueError("JobPosting has no valid application URL")

    return JobData(
        source=_source_name(source_url),
        external_id=extract_identifier(posting.get("identifier")),
        title=title[:500],
        company=company,
        location=location,
        description=description,
        requirements=requirements,
        salary=extract_salary(posting),
        employment_type=_join_values(posting.get("employmentType"), limit=100),
        apply_url=apply_url,
        source_url=source_url,
        posted_at=parse_date(posting.get("datePosted")),
    )


def extract_identifier(value: Any) -> str | None:
    if isinstance(value, (str, int)):
        return str(value)[:255]
    if isinstance(value, dict):
        identifier = value.get("value") or value.get("name") or value.get("@id")
        if isinstance(identifier, (str, int)):
            return str(identifier)[:255]
    return None


def extract_organization_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = clean_html(value.get("name") or value.get("legalName"))
    if not name:
        return None
    name = " ".join(name.split())
    bad_phrases = ("company description", "about the company", "cookie")
    if len(name) > 300 or any(phrase in name.lower() for phrase in bad_phrases):
        return None
    return name


def extract_location(
    value: Any,
    *,
    job_location_type: Any = None,
    applicant_requirements: Any = None,
) -> str | None:
    physical = _extract_locations(value)
    is_remote = _contains_remote(job_location_type)
    applicant_locations = _extract_locations(applicant_requirements)

    if is_remote:
        if applicant_locations:
            remote_values = [f"Remote - {item}" for item in applicant_locations]
        else:
            remote_values = ["Remote"]
        values = remote_values + physical
    else:
        values = physical or applicant_locations

    clean_values = []
    for item in values:
        item = " ".join(item.split()).strip(" ,-|")
        if item and item.lower() not in {"none", "null"}:
            clean_values.append(item[:500])
    return " | ".join(dict.fromkeys(clean_values)) or None


def _extract_locations(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_extract_locations(item))
        return result
    if not isinstance(value, dict):
        return []

    if "address" in value:
        address_values = _extract_locations(value["address"])
        if address_values:
            return address_values

    parts = []
    for key in ("addressLocality", "addressRegion", "addressCountry"):
        part = value.get(key)
        if isinstance(part, dict):
            part = part.get("name") or part.get("value")
        if isinstance(part, (str, int)) and str(part).strip():
            parts.append(str(part).strip())
    if parts:
        return [", ".join(dict.fromkeys(parts))]

    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return [name.strip()]
    return []


def _contains_remote(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_remote(item) for item in value)
    return isinstance(value, str) and any(
        marker in value.lower()
        for marker in ("telecommute", "remote", "work from home")
    )


def parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def extract_salary(posting: dict[str, Any]) -> str | None:
    salary = posting.get("baseSalary") or posting.get("estimatedSalary")
    if not isinstance(salary, dict):
        return clean_html(salary)

    currency = salary.get("currency") or posting.get("salaryCurrency") or ""
    value = salary.get("value", salary)
    if not isinstance(value, dict):
        text = clean_html(value)
        return f"{text} {currency}".strip() if text else None

    minimum = value.get("minValue")
    maximum = value.get("maxValue")
    exact = value.get("value")
    unit = value.get("unitText") or ""
    if minimum is not None and maximum is not None:
        amount = f"{minimum} - {maximum}"
    elif minimum is not None:
        amount = f"From {minimum}"
    elif maximum is not None:
        amount = f"Up to {maximum}"
    elif exact is not None:
        amount = str(exact)
    else:
        return None
    suffix = " ".join(str(item) for item in (currency, unit) if item)
    return f"{amount} {suffix}".strip()[:300]


def extract_fallback_job(
    html: str,
    source_url: str,
    search_title: str | None = None,
) -> JobData | None:
    """Extract only pages with strong, page-level job evidence.

    ``search_title`` is intentionally ignored: search-result titles are not
    trusted as job data.
    """
    del search_title
    if is_job_listing_page(source_url) or is_disallowed_job_url(source_url):
        return None

    soup = BeautifulSoup(html, "lxml")
    title = extract_page_title(soup)
    if not title or _bad_title(title):
        return None

    text = soup.get_text("\n", strip=True)
    apply_url = extract_apply_url(soup, source_url)
    explicit_apply = apply_url != source_url or bool(
        soup.find("form", attrs={"action": re.compile("apply", re.I)})
    )
    if not explicit_apply or not looks_like_job_page(text):
        return None

    host = (urlparse(source_url).hostname or "").lower().removeprefix("www.")
    has_job_metadata = bool(
        soup.select_one('[itemprop="datePosted"], meta[name="job:location"]')
    )
    job_specific_path = bool(
        re.search(
            r"/(jobs?|careers?|positions?)/[^/?#]+",
            urlparse(source_url).path,
            re.I,
        )
    )
    if host not in KNOWN_JOB_HOSTS and not (has_job_metadata or job_specific_path):
        return None

    return JobData(
        source=_source_name(source_url),
        external_id=None,
        title=title[:500],
        company=extract_company(soup),
        location=extract_fallback_location(soup),
        description=extract_description(soup, text),
        requirements=extract_section(
            text,
            [
                "requirements",
                "qualifications",
                "what we're looking for",
                "what you will need",
            ],
        ),
        salary=None,
        employment_type=None,
        apply_url=apply_url,
        source_url=source_url,
        posted_at=extract_fallback_date(soup),
    )


def extract_page_title(
    soup: BeautifulSoup,
    search_title: str | None = None,
) -> str | None:
    del search_title
    heading = soup.find("h1")
    if heading:
        value = heading.get_text(" ", strip=True)
        if value:
            return " ".join(value.split())
    meta = soup.select_one('meta[property="og:title"], meta[name="twitter:title"]')
    if meta and meta.get("content"):
        return " ".join(str(meta["content"]).split())
    return None


def looks_like_job_page(text: str) -> bool:
    text_lower = " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())
    if any(phrase in text_lower for phrase in NON_JOB_CONTENT_PHRASES):
        return False
    signals = {
        "apply for this job",
        "apply now",
        "benefits",
        "employment type",
        "full time",
        "part time",
        "qualifications",
        "requirements",
        "responsibilities",
        "submit application",
        "years of experience",
    }
    return sum(signal in text_lower for signal in signals) >= 4


def extract_company(soup: BeautifulSoup) -> str | None:
    selectors = (
        '[itemprop="hiringOrganization"] [itemprop="name"]',
        '[data-company-name]',
        'meta[name="company"]',
        'meta[property="og:site_name"]',
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue
        value = element.get("content") or element.get("data-company-name")
        if value is None:
            value = element.get_text(" ", strip=True)
        name = " ".join(str(value).split())
        if 1 < len(name) <= 300 and not any(
            phrase in name.lower()
            for phrase in ("company description", "cookie", "job board")
        ):
            return name
    return None


def extract_fallback_location(soup: BeautifulSoup) -> str | None:
    selectors = (
        '[itemprop="jobLocation"]',
        '[data-job-location]',
        'meta[name="job:location"]',
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue
        value = element.get("content") or element.get("data-job-location")
        if value is None:
            value = element.get_text(" ", strip=True)
        location = " ".join(str(value).split()).strip()
        if 1 < len(location) <= 500 and "cookie" not in location.lower():
            return location
    return None


def extract_section(text: str, headings: list[str]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start_index = next(
        (
            index
            for index, line in enumerate(lines)
            if any(heading in line.lower() for heading in headings)
        ),
        None,
    )
    if start_index is None:
        return None
    section: list[str] = []
    for line in lines[start_index + 1 :]:
        if len(section) >= 30:
            break
        if line.endswith(":") and len(section) >= 3:
            break
        section.append(line)
    return "\n".join(section)[:5000] or None


def extract_description(soup: BeautifulSoup, text: str) -> str | None:
    selectors = (
        '[itemprop="description"]',
        '[class*="job-description"]',
        '[id*="job-description"]',
        "main",
    )
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            value = element.get_text("\n", strip=True)
            if len(value) >= 100:
                return value[:10000]
    return text[:10000] or None


def extract_apply_url(soup: BeautifulSoup, source_url: str) -> str:
    for link in soup.find_all("a", href=True):
        label = " ".join(link.get_text(" ", strip=True).lower().split())
        if not re.search(r"\b(apply|submit application)\b", label):
            continue
        candidate = _absolute_http_url(link.get("href"), source_url)
        if candidate:
            return candidate
    return source_url


def extract_fallback_date(soup: BeautifulSoup) -> datetime | None:
    element = soup.select_one(
        '[itemprop="datePosted"], meta[name="datePosted"], meta[name="job:datePosted"]'
    )
    if not element:
        return None
    value = element.get("content") or element.get("datetime")
    if value is None:
        value = element.get_text(" ", strip=True)
    return parse_date(str(value))


def is_job_listing_page(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    query = parsed.query.lower()
    listing_paths = {
        "/careers",
        "/jobs",
        "/job-search",
        "/open-positions",
        "/positions",
    }
    single_job_parameters = ("gh_jid=", "job_id=", "jobid=", "position_id=")
    if path in listing_paths and not any(key in query for key in single_job_parameters):
        return True
    if any(
        pattern in path
        for pattern in (
            "/career-advice/",
            "/categories/",
            "/jobs-by-title/",
            "/job-search/",
        )
    ):
        return True
    return any(key in query for key in ("query=", "search=", "keyword="))


def is_disallowed_job_url(url: str) -> bool:
    if _is_blocked_host(url):
        return True
    path = urlparse(url).path.lower()
    return any(
        marker in path
        for marker in (
            "/article/",
            "/articles/",
            "/blog/",
            "/career-advice/",
            "/forum/",
            "/guide/",
            "/guides/",
            "/tutorial/",
        )
    )


def _bad_title(title: str) -> bool:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())
    return any(phrase in normalized for phrase in NON_JOB_TITLE_PHRASES)


def _is_blocked_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_HOSTS)


def _source_name(url: str) -> str:
    host = (urlparse(url).hostname or "web").lower().removeprefix("www.")
    return host[:100]


def _absolute_http_url(value: Any, base_url: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = urljoin(base_url, value.strip())
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def _join_values(value: Any, *, limit: int) -> str | None:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(dict.fromkeys(parts))[:limit] or None
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value).strip()[:limit]
    return None
