from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.ai.resume_analyzer import analyze_resume
from app.config import Settings
from app.database import SessionLocal
from app.models import CandidateProfile, ResumeVersion, UserProfile
from app.resume.parser import extract_resume_text
from app.resume.profile_service import save_candidate_profile
from app.scheduler import ProfileScheduler
from app.worker import JobSearchRunner


logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    db: Session = SessionLocal()
    try:
        profile = _get_profile(db, chat_id)
        if not profile:
            profile = UserProfile(
                name=update.effective_user.first_name if update.effective_user else "Job seeker",
                telegram_chat_id=chat_id,
                minimum_match=75,
                search_enabled=True,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        await update.message.reply_text(
            "👋 Job-Find-Me is connected.\n\n"
            "Upload a PDF or DOCX resume, then configure your search with /set.\n"
            "Use /settings to see examples and /status to check the service."
        )
    except Exception:
        db.rollback()
        logger.exception("Could not create Telegram profile")
        await update.message.reply_text("❌ I could not create your profile.")
    finally:
        db.close()


async def handle_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not update.message or not update.effective_chat:
        return
    document = update.message.document
    if not document:
        return

    original_name = Path(document.file_name or "resume").name
    extension = Path(original_name).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        await update.message.reply_text("❌ Upload your resume as a PDF or DOCX file.")
        return

    db: Session = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Send /start before uploading a resume.")
            return

        storage_dir = Settings.from_environment().resume_storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        file_path = storage_dir / f"profile_{profile.id}_{timestamp}_{original_name}"

        telegram_file = await document.get_file()
        await telegram_file.download_to_drive(custom_path=str(file_path))
        await update.message.reply_text("📄 Resume received. Extracting and analysing it…")

        resume_text = await asyncio.to_thread(extract_resume_text, str(file_path))
        if not resume_text.strip():
            await update.message.reply_text(
                "❌ No readable text was found. Scanned PDFs need OCR before upload."
            )
            return

        analysis = await asyncio.to_thread(analyze_resume, resume_text)
        db.add(
            ResumeVersion(
                profile_id=profile.id,
                filename=original_name,
                file_path=str(file_path),
                extracted_text=resume_text,
            )
        )
        profile.resume_text = resume_text
        if not profile.target_titles and analysis.job_titles:
            profile.target_titles = ", ".join(analysis.job_titles[:5])
        db.commit()
        save_candidate_profile(
            db=db,
            profile_id=profile.id,
            analysis=analysis,
        )

        await update.message.reply_text(
            "✅ Resume analysed and candidate profile saved.\n\n"
            f"🎯 Titles: {', '.join(analysis.job_titles[:5]) or 'None found'}\n"
            f"🛠 Skills: {', '.join(analysis.skills[:8]) or 'None found'}\n\n"
            "Review search preferences with /settings."
        )
    except Exception:
        db.rollback()
        logger.exception("Resume processing failed")
        await update.message.reply_text(
            "❌ Resume processing failed. Check the service log and Groq configuration."
        )
    finally:
        db.close()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not update.message or not update.effective_chat:
        return
    db = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Profile not found. Send /start first.")
            return
        candidate = (
            db.query(CandidateProfile)
            .filter(CandidateProfile.profile_id == profile.id)
            .first()
        )
        await update.message.reply_text(
            "<b>JOB-FIND-ME STATUS</b>\n\n"
            f"📄 Resume: {'Uploaded' if profile.resume_text else 'Not uploaded'}\n"
            f"🧠 Candidate profile: {'Ready' if candidate else 'Not ready'}\n"
            f"🎯 Minimum match: {profile.minimum_match}%\n"
            f"🔎 Searching: {'ON' if profile.search_enabled else 'OFF'}\n"
            f"⏱ Search interval: {profile.search_interval_minutes} minutes\n"
            f"🕒 Maximum job age: {profile.max_job_age_hours} hours\n"
            "📱 Telegram: Connected",
            parse_mode="HTML",
        )
    finally:
        db.close()


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not update.message or not update.effective_chat:
        return
    db = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Profile not found. Send /start first.")
            return
        await update.message.reply_text(
            "⚙️ <b>SEARCH SETTINGS</b>\n\n"
            f"Titles: {escape(profile.target_titles or 'Not set')}\n"
            f"Locations: {escape(profile.locations or 'Not set')}\n"
            f"Remote preference: {escape(profile.remote_preference or 'No restriction')}\n"
            f"Minimum match: {profile.minimum_match}%\n"
            f"Maximum age: {profile.max_job_age_hours} hours\n"
            f"Interval: {profile.search_interval_minutes} minutes\n"
            f"Daily limit: {profile.max_notifications_per_day}\n\n"
            "Update examples:\n"
            "<code>/set titles Backend Developer, Python Developer</code>\n"
            "<code>/set locations Nigeria, Remote</code>\n"
            "<code>/set minimum_match 75</code>\n"
            "<code>/set remote_preference preferred</code>\n"
            "<code>/set max_job_age_hours 24</code>\n"
            "<code>/set search_interval_minutes 30</code>\n"
            "<code>/set max_notifications_per_day 50</code>",
            parse_mode="HTML",
        )
    finally:
        db.close()


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Use /settings to see valid /set examples.")
        return
    key = context.args[0].lower()
    raw_value = " ".join(context.args[1:]).strip()
    db = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Profile not found. Send /start first.")
            return
        display_value = _apply_setting(profile, key, raw_value)
        db.commit()
        await update.message.reply_text(f"✅ {key} updated to: {display_value}")
    except ValueError as error:
        db.rollback()
        await update.message.reply_text(f"❌ {error}")
    except Exception:
        db.rollback()
        logger.exception("Could not update profile setting")
        await update.message.reply_text("❌ The setting could not be saved.")
    finally:
        db.close()


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _set_search_enabled(update, False)


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _set_search_enabled(update, True)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    db = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Profile not found. Send /start first.")
            return
        profile_id = profile.id
        chat_id = update.effective_chat.id
    finally:
        db.close()

    runner: JobSearchRunner = context.application.bot_data["job_runner"]
    await update.message.reply_text("🔎 Starting a search cycle…")

    async def run_and_report() -> None:
        stats = await runner.run_profile(profile_id, require_enabled=False)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ Search cycle complete.\n"
                f"Valid jobs: {stats.discovered}\n"
                f"Evaluated: {stats.matched}\n"
                f"Notifications: {stats.notified}"
            ),
        )

    context.application.create_task(run_and_report())


def create_bot(
    runner: JobSearchRunner | None = None,
    scheduler: ProfileScheduler | None = None,
) -> Application:
    token = Settings.from_environment().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    runner = runner or JobSearchRunner()
    scheduler = scheduler or ProfileScheduler(runner)

    async def post_init(application: Application) -> None:
        application.bot_data["scheduler_task"] = application.create_task(
            scheduler.run_forever()
        )

    async def post_shutdown(application: Application) -> None:
        task: asyncio.Task[Any] | None = application.bot_data.get("scheduler_task")
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["job_runner"] = runner
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("set", set_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_resume))
    return application


def _get_profile(db: Session, chat_id: int) -> UserProfile | None:
    return (
        db.query(UserProfile)
        .filter(UserProfile.telegram_chat_id == chat_id)
        .first()
    )


async def _set_search_enabled(update: Update, enabled: bool) -> None:
    if not update.message or not update.effective_chat:
        return
    db = SessionLocal()
    try:
        profile = _get_profile(db, update.effective_chat.id)
        if not profile:
            await update.message.reply_text("❌ Profile not found. Send /start first.")
            return
        profile.search_enabled = enabled
        db.commit()
        await update.message.reply_text(
            "▶️ Scheduled searching resumed." if enabled else "⏸ Scheduled searching stopped."
        )
    finally:
        db.close()


def _apply_setting(profile: UserProfile, key: str, raw_value: str) -> str:
    text_fields = {
        "titles": "target_titles",
        "target_titles": "target_titles",
        "locations": "locations",
    }
    integer_ranges = {
        "minimum_match": ("minimum_match", 0, 100),
        "max_job_age_hours": ("max_job_age_hours", 1, 24 * 30),
        "search_interval_minutes": ("search_interval_minutes", 1, 24 * 60),
        "max_notifications_per_day": ("max_notifications_per_day", 1, 500),
    }
    if key in text_fields:
        if len(raw_value) > 1000:
            raise ValueError("That value is too long")
        setattr(profile, text_fields[key], raw_value)
        return raw_value
    if key == "remote_preference":
        value = raw_value.lower()
        aliases = {"remote": "required", "yes": "required", "office": "onsite"}
        value = aliases.get(value, value)
        allowed = {"required", "preferred", "onsite", "none"}
        if value not in allowed:
            raise ValueError(
                "remote_preference must be required, preferred, onsite, or none"
            )
        profile.remote_preference = None if value == "none" else value
        return "No restriction" if value == "none" else value
    if key in integer_ranges:
        field, minimum, maximum = integer_ranges[key]
        try:
            value = int(raw_value)
        except ValueError as error:
            raise ValueError(f"{key} must be a whole number") from error
        if not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        setattr(profile, field, value)
        return str(value)
    raise ValueError(f"Unknown setting: {key}")
