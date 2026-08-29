from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from html import escape
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.constants import ParseMode

from app.config import Settings
from app.models import Job, JobMatch, UserProfile


logger = logging.getLogger(__name__)
MessageSender = Callable[[int, str], Awaitable[Any]]


async def send_telegram_message(chat_id: int, message: str) -> None:
    token = Settings.from_environment().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    async with Bot(token=token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


def format_job_notification(job: Job, match: JobMatch) -> str:
    matched = _format_skill_list(match.matched_skills, "•")
    missing = _format_skill_list(match.missing_skills, "•")
    company = escape((job.company or "Company not provided")[:150])
    location = escape((job.location or "Location not provided")[:250])
    salary = escape((job.salary or "Not provided")[:150])
    employment = escape((job.employment_type or "Not provided")[:100])
    explanation = escape((match.explanation or "No explanation provided")[:700])
    apply_url = escape(job.apply_url, quote=True)
    divider = "━━━━━━━━━━━━━━━━━━"

    message = (
        "🚨 <b>NEW JOB MATCH</b>\n\n"
        f"🎯 <b>Match: {match.score:.1f}%</b>\n\n"
        f"💼 <b>{escape(job.title[:200])}</b>\n"
        f"🏢 {company}\n"
        f"📍 {location}\n"
        f"🕒 Posted: {escape(format_posted_date(job.posted_at))}\n"
        f"💰 Salary: {salary}\n"
        f"🧾 Employment: {employment}\n\n"
        f"{divider}\n\n"
        f"✅ <b>MATCHED SKILLS</b>\n{matched}\n\n"
        f"❌ <b>MISSING SKILLS</b>\n{missing}\n\n"
        f"{divider}\n\n"
        "📊 <b>SCORE BREAKDOWN</b>\n\n"
        f"Skills: {match.skills_score:.1f}%\n"
        f"Experience: {match.experience_score:.1f}%\n"
        f"Title: {match.title_score:.1f}%\n"
        f"Education: {match.education_score:.1f}%\n"
        f"Location: {match.location_score:.1f}%\n\n"
        f"{divider}\n\n"
        f"🧠 <b>WHY IT MATCHES</b>\n\n{explanation}\n\n"
        f"{divider}\n\n"
        f'🔗 <a href="{apply_url}"><b>APPLY NOW</b></a>'
    )
    return message


def format_posted_date(posted_at: datetime | None) -> str:
    if posted_at is None:
        return "Unknown"
    posted = _as_utc(posted_at)
    now = datetime.now(timezone.utc)
    age_seconds = max(0, int((now - posted).total_seconds()))
    if age_seconds < 3600:
        relative = f"{max(1, age_seconds // 60)} minutes ago"
    elif age_seconds < 86400:
        relative = f"{age_seconds // 3600} hours ago"
    else:
        days = age_seconds // 86400
        relative = f"{days} day{'s' if days != 1 else ''} ago"
    absolute = posted.strftime("%B %d, %Y at %I:%M %p UTC")
    return f"{relative} ({absolute})"


def count_notifications_today(db: Session, profile_id: int) -> int:
    day_start = datetime.now(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=None,
    )
    return int(
        db.query(func.count(JobMatch.id))
        .filter(
            JobMatch.profile_id == profile_id,
            JobMatch.notified.is_(True),
            JobMatch.notified_at >= day_start,
        )
        .scalar()
        or 0
    )


async def notify_qualifying_match(
    db: Session,
    profile: UserProfile,
    job: Job,
    match: JobMatch,
    *,
    sender: MessageSender = send_telegram_message,
) -> bool:
    if match.notified or match.score < profile.minimum_match:
        return False
    if not profile.telegram_chat_id:
        logger.warning("Profile %s has no Telegram chat ID", profile.id)
        return False
    if count_notifications_today(db, profile.id) >= profile.max_notifications_per_day:
        logger.info("Daily notification limit reached for profile %s", profile.id)
        return False

    try:
        await sender(
            profile.telegram_chat_id,
            format_job_notification(job, match),
        )
    except Exception:
        logger.exception("Telegram delivery failed for match %s", match.id)
        return False

    match.notified = True
    match.notified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        db.commit()
        db.refresh(match)
    except Exception:
        db.rollback()
        logger.exception("Could not persist notification state for match %s", match.id)
        return False
    logger.info("Telegram notification sent for match %s", match.id)
    return True


def _format_skill_list(values: list | None, marker: str) -> str:
    if not values:
        return "• None identified"
    return "\n".join(
        f"{marker} {escape(str(value))}"
        for value in (str(item)[:80] for item in values[:8])
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
