# Job-Find-Me

Job-Find-Me is a backend-only personal job-search service. You upload a resume through Telegram, configure the roles and locations you want, and leave the process running. It searches the public web with Tavily, verifies actual job pages, stores and filters jobs in PostgreSQL, asks Groq to score suitable jobs, and sends qualifying matches to Telegram.

There is no dashboard or web/mobile UI. Telegram is the interface and `python -m app.main` is the service entry point.

## How it works

```text
Resume (PDF/DOCX via Telegram)
        ↓
Extracted resume text → CandidateProfile (Groq)
        ↓
Profile titles + locations + remote preference
        ↓
Tavily public-web search
        ↓
Fetch page → validate JobPosting JSON-LD / strong job-page evidence
        ↓
Normalize + deduplicate → PostgreSQL Job
        ↓
Title + location + remote + posted-date filters
        ↓
Groq structured match analysis → PostgreSQL JobMatch
        ↓
Minimum score + daily limit + not-already-notified checks
        ↓
Telegram notification → notified=True only after successful delivery
```

The scheduler reads each enabled profile's own `search_interval_minutes`. A failed page, malformed JSON-LD document, invalid Groq response, or temporary Telegram problem is logged without stopping the rest of the cycle.

## Requirements

- Windows 10 or 11 with PowerShell
- Python 3.12 or newer (the project is currently tested with Python 3.14)
- PostgreSQL 14 or newer
- A Telegram account and bot token
- A Tavily account and API key
- A Groq account and API key

## 1. Get the project

```powershell
git clone <repository-url>
cd Job-Find-Me
```

If the project folder was provided directly, open PowerShell in that folder instead.

## 2. Create the virtual environment

```powershell
python -m venv .venv
```

Activate it when PowerShell permits scripts:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If activation is blocked by the PowerShell execution policy, activation is optional. Use the environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For a temporary activation-policy change in only the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 3. Install and configure PostgreSQL

Install PostgreSQL for Windows and remember the password assigned to the `postgres` administrator. Ensure the PostgreSQL Windows service is running.

Open `psql` or the SQL shell as the `postgres` user and create a dedicated database and user:

```sql
CREATE USER job_find_me_user WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE job_find_me OWNER job_find_me_user;
```

The connection URL will look like:

```env
DATABASE_URL=postgresql+psycopg2://job_find_me_user:choose-a-strong-password@localhost:5432/job_find_me
```

URL-encode special characters in the username or password. For example, `@` becomes `%40` and `#` becomes `%23`.

## 4. Create `.env`

Copy the template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set every required value:

| Variable | Required | Purpose |
|---|---:|---|
| `DATABASE_URL` | Yes | SQLAlchemy PostgreSQL connection URL |
| `TAVILY_API_KEY` | Yes | Searches indexed public job pages |
| `GROQ_API_KEY` | Yes | Resume extraction and job-match analysis |
| `GROQ_MODEL` | No | Groq model; defaults to `openai/gpt-oss-20b` |
| `TELEGRAM_BOT_TOKEN` | Yes | Sends commands and job notifications through your bot |
| `RESUME_STORAGE_DIR` | No | Local resume directory; defaults to `storage/resumes` |
| `SEARCH_RESULTS_PER_QUERY` | No | Tavily results requested per generated query; defaults to `5` |
| `SCHEDULER_POLL_SECONDS` | No | How often the scheduler checks which profile is due; defaults to `30` |

Never commit `.env`. It and uploaded resumes are ignored by Git.

### Groq setup

1. Create/sign in to a Groq account.
2. Create an API key in the Groq console.
3. Put it in `.env` as `GROQ_API_KEY`.
4. Leave `GROQ_MODEL=openai/gpt-oss-20b`, or replace it with another model available to your account that supports structured JSON output.

Keys are loaded at runtime and are never hardcoded or logged.

### Tavily setup

1. Create/sign in to Tavily.
2. Create an API key.
3. Put it in `.env` as `TAVILY_API_KEY`.

Tavily discovers URLs; Job-Find-Me still fetches and validates the actual page. A result title and snippet alone never become a job.

### Telegram setup

1. In Telegram, open a chat with `@BotFather`.
2. Send `/newbot` and follow the prompts.
3. Copy the bot token into `.env` as `TELEGRAM_BOT_TOKEN`.
4. Start Job-Find-Me using the command in the Running section below.
5. Open your new bot and send `/start`.

The `/start` command obtains the chat ID from Telegram and stores it on your `UserProfile`; no separate chat-ID environment variable is needed.

## 5. Apply database migrations

With the virtual environment activated:

```powershell
python -m alembic upgrade head
```

Without activation:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Alembic creates or upgrades the tables without deleting the database. The migrations safely add populated-profile settings with server defaults and enforce one `JobMatch` per profile/job. Check the installed revision with:

```powershell
python -m alembic current
python -m alembic check
```

## 6. Run the application

```powershell
python -m app.main
```

Or, without activating the environment:

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Keep that process running. It validates required environment variables, checks the database connection, starts Telegram polling, and starts the recurring search scheduler. Press `Ctrl+C` to stop it cleanly.

## 7. Upload the resume and configure the profile

In the Telegram bot:

1. Send `/start`.
2. Attach a PDF or DOCX resume as a document.
3. Wait for confirmation that the CandidateProfile was created.
4. Send `/settings` and update the search preferences.

Examples:

```text
/set titles Backend Developer, Python Developer, Software Engineer
/set locations Nigeria, Remote
/set remote_preference preferred
/set minimum_match 75
/set max_job_age_hours 24
/set search_interval_minutes 30
/set max_notifications_per_day 50
```

Available commands:

| Command | Action |
|---|---|
| `/start` | Create/connect the Telegram profile |
| `/status` | Show resume, AI profile, schedule, age, and search state |
| `/settings` | Show current preferences and `/set` examples |
| `/set <setting> <value>` | Update a preference |
| `/search` | Run one search immediately, even if the schedule is paused |
| `/stop` | Pause recurring searches |
| `/resume` | Resume recurring searches |

If target titles are empty when a resume is uploaded, the first few job titles extracted from the resume are used as a starting point. Review them with `/settings`.

### Preference behavior

- `minimum_match`: inclusive threshold. `75.0` sends when the setting is 75; `74.9` does not.
- `max_job_age_hours`: only a real extracted posting date is accepted. Missing dates are not treated as recent and are not automatically notified.
- `search_interval_minutes`: independent schedule for this profile; it is never hardcoded to 30.
- `locations`: comma-separated acceptable places. `Nigeria, Remote` accepts Nigeria, unrestricted remote, worldwide remote, and Africa-scoped remote, but rejects country-restricted remote roles such as `Remote - Paraguay`.
- `remote_preference`: use `required`, `preferred`, `onsite`, or leave it unrestricted.
- `max_notifications_per_day`: counts only successfully delivered notifications, using `notified_at`.

## Telegram notification example

```text
🚨 NEW JOB MATCH

🎯 Match: 86.5%
💼 Backend Developer
🏢 Example Company
📍 Lagos, Nigeria
🕒 Posted: 6 hours ago (August 28, 2026 at 02:15 PM UTC)
💰 Salary: $50,000 - $70,000

✅ MATCHED SKILLS
• Python
• FastAPI
• PostgreSQL

❌ MISSING SKILLS
• AWS

📊 SCORE BREAKDOWN
Skills: 90.0%
Experience: 85.0%
Title: 95.0%
Education: 100.0%
Location: 80.0%

🔗 APPLY NOW
```

`APPLY NOW` is a clickable link to the structured job URL or the best verified application link found on the page.

## Tests

The required tests are deterministic and mock external services. They do not spend Tavily/Groq quota or send Telegram messages.

```powershell
python -m app.discovery.test_discovery
python -m app.jobs.test_filters
python -m app.matching.test_match
python -m app.matching.test_pipeline
python -m app.telegram.test_notifications
python -m app.test_worker
```

Run every test module together:

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

Optional live integration scripts use your real configuration and quota:

```powershell
python -m app.discovery.test_search
python -m app.discovery.test_pipeline
python -m app.matching.test_real_match
```

## Clean invalid legacy jobs safely

The cleanup command uses conservative title/URL rules and defaults to preview mode:

```powershell
python -m app.jobs.cleanup_invalid
```

Review every listed row. To deactivate those rows (without deleting them or their match history):

```powershell
python -m app.jobs.cleanup_invalid --apply
```

Deactivated records remain recoverable in PostgreSQL and are excluded from new processing.

## Project structure

```text
Job-Find-Me/
├── alembic/                    # Ordered PostgreSQL schema migrations
├── app/
│   ├── ai/                     # Lazy Groq client and resume analysis
│   ├── discovery/              # Query building, Tavily, page fetch/extraction
│   ├── jobs/                   # Job schema, normalization, dedupe, filters, cleanup
│   ├── matching/               # Strict AI analysis and JobMatch persistence
│   ├── resume/                 # PDF/DOCX text extraction and CandidateProfile save
│   ├── telegram/               # Bot commands, formatting, delivery guarantees
│   ├── config.py               # Environment settings
│   ├── database.py             # SQLAlchemy engine and sessions
│   ├── models.py               # Persistent models
│   ├── scheduler.py            # Dynamic per-profile recurring schedule
│   ├── worker.py               # End-to-end search/match/notify cycle
│   └── main.py                 # Single service entry point
├── storage/resumes/            # Local uploads; ignored by Git
├── .env.example
├── alembic.ini
├── requirements.txt
└── README.md
```

## Troubleshooting

### PowerShell will not activate `.venv`

Use `.\.venv\Scripts\python.exe` directly for every command, or temporarily run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`. Avoid changing machine-wide policy unless you understand the impact.

### PostgreSQL connection errors

- Confirm the PostgreSQL Windows service is running.
- Verify the host, port (normally 5432), database, user, and password.
- URL-encode special characters in credentials.
- Test with `python -m alembic current`; it uses the same `DATABASE_URL`.

### Alembic migration errors

Run:

```powershell
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
```

Do not delete the database or stamp a revision blindly. Save the complete error and inspect the current revision first. The included migrations use server defaults when introducing required settings to existing profiles.

### Missing `GROQ_API_KEY` or invalid Groq responses

Confirm the key and `GROQ_MODEL` in `.env`, then restart the process. The matcher retries malformed JSON and skips only the affected job after repeated invalid responses. Check that the configured model is available to your Groq account.

### Missing `TAVILY_API_KEY` or no search results

Verify the key, Tavily quota, and that `/settings` shows target titles. Try `/search` and inspect the log's generated queries and result counts.

### Telegram bot does not respond

- Confirm `TELEGRAM_BOT_TOKEN` exactly matches BotFather's token.
- Make sure only one copy of this bot is polling at a time.
- Send `/start` directly to the bot (bots cannot initiate the first chat).
- Restart `python -m app.main` after changing `.env`.

### Websites return 403 or 429

This is expected for some sites. Job-Find-Me uses a normal timeout, redirect handling, and user agent but does not bypass anti-bot controls. It logs the URL and continues with other public sources.

### No CandidateProfile found

Upload a text-based PDF or DOCX through Telegram. Image-only/scanned PDFs require OCR before upload. Watch the service log for a Groq or extraction error.

### Jobs are found but none pass filters

Check `/settings`, especially target titles, locations, remote preference, and `max_job_age_hours`. Jobs with no reliable `datePosted` are deliberately not considered fresh. Widen settings carefully instead of treating unknown dates or locations as matches.

### No notifications arrive

The job must pass deterministic filters and the Groq score must be greater than or equal to `minimum_match`. It must also be below the daily successful-notification limit and not have been notified before. Telegram failures leave `notified=False`, so a later cycle can retry.

## Security and operating notes

- Keep `.env`, uploaded resumes, database backups, and logs private.
- Rotate any API token that may have been exposed.
- Run `alembic upgrade head` before starting a newly updated checkout.
- Back up PostgreSQL before manual maintenance.
- The extractor only requests publicly accessible pages and does not attempt to defeat access controls.
