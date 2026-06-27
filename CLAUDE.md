# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal productivity web app that runs as a local server on macOS. It tracks tasks, notes, a school timetable fetched from WebUntis, booked Mudo training sessions, and syncs with Apple Reminders and Apple Notes. The user opens it in a browser at `http://localhost:8000`. It can also be deployed to the cloud on Render + Supabase (see `DEPLOY.md`).

## Tech stack

| Layer | Tool |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| Storage | SQLite at `~/.local/share/taskboard/data.db` locally; Postgres (Supabase) in the cloud when `DATABASE_URL` is set |
| Browser automation | Playwright (Chromium, headed, persistent profiles) |
| Apple integration | `osascript` / JXA — no extra packages needed |
| Frontend | Vanilla HTML/CSS/JS — single file `static/index.html`, no build step |
| Package manager | uv |

## File structure

```
main.py              # FastAPI app — all routes and models
db.py                # Database layer — SQLite / Postgres abstraction via get_db()
webuntis.py          # Playwright automation for syncing timetable + messages
mudo.py              # Playwright automation for syncing Mudo.se training bookings
reminders.py         # Apple Reminders + Apple Notes integration via osascript / JXA
static/index.html    # Entire frontend (HTML + CSS + JS in one file)
pyproject.toml       # Dependencies and project metadata
INTERFACE.md         # Frontend / UI documentation (tab layout, JS functions, state)
WEBUNTIS.md          # WebUntis integration documentation (API endpoints, data format)
DEPLOY.md            # Instructions for deploying to Render + Supabase
render.yaml          # Render Blueprint configuration
requirements.txt     # pip-compatible deps for Render build
```

Data is stored outside the project directory in `~/.local/share/taskboard/data.db` so it is never accidentally committed.

## How to run

```bash
# First time only — install Chromium for Playwright:
uv run playwright install chromium

# Start the server:
uv run python main.py
```

Server listens on `0.0.0.0:8000` with hot-reload enabled (hot-reload is disabled automatically when running on Render via `$PORT`).

```bash
# Inspect the database directly:
sqlite3 ~/.local/share/taskboard/data.db

# Add a new dependency:
uv add <package>
```

There are no tests in this project.

## Database layer (`db.py`)

`db.py` provides a unified `get_db()` context manager used by all routes in `main.py`. It checks the `DATABASE_URL` environment variable at import time:

- **Unset** → uses local SQLite at `~/.local/share/taskboard/data.db`
- **Set** → uses Postgres via `psycopg`

`db.py` wraps connections in a `Conn` class that translates `?` placeholders to `%s` for Postgres. The rest of the app always writes `?`-style SQL.

`init_db()` and `migrate_db()` are also in `db.py` and are called on startup via the `lifespan` handler in `main.py`.

### Adding new DB columns

New columns go in `CREATE TABLE IF NOT EXISTS` inside `init_db()` **and** as an `ALTER TABLE` statement inside `migrate_db()`. `migrate_db()` catches and ignores "column already exists" errors (on SQLite) and uses `ADD COLUMN IF NOT EXISTS` on Postgres. Both are safe to re-run.

## Database schema

Five tables, created automatically on first run.

**tasks**
- `id`, `title`, `description`, `due_date` (YYYY-MM-DD), `priority` (low/medium/high), `done` (0/1), `created_at`
- `webuntis_id` (nullable — set for homework tasks synced from WebUntis, e.g. `"hw_123"`)
- `reminders_id` (nullable — set for tasks pulled from Apple Reminders; stores the Apple reminder's UUID)

**notes**
- `id`, `title`, `content`, `created_at`, `updated_at`
- `apple_notes_id` (nullable — set for notes pulled from Apple Notes)

**schedule_lessons**
- `id`, `date` (YYYY-MM-DD), `start_time` (HH:MM), `end_time` (HH:MM), `subject`, `teacher`, `room`, `cancelled` (0/1), `lesson_code` (REGULAR/CANCELLED/IRREGULAR/SUBSTITUTION/FREE), `synced_at`

**messages**
- `id` (WebUntis message ID, primary key), `subject`, `body` (HTML), `sender`, `sent_at`, `is_read` (0/1), `synced_at`

**mudo_bookings**
- `id` (TEXT, `"YYYY-MM-DD_HH:MM_title"` composite key), `date` (YYYY-MM-DD), `start_time` (HH:MM), `duration_min` (INTEGER, nullable), `title`, `instructors` (comma-separated), `room`, `status` (`booked` or `waitlist`), `synced_at`

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves `static/index.html` |
| GET | `/api/tasks` | List all tasks (active first, then done) |
| POST | `/api/tasks` | Create task |
| PUT | `/api/tasks/{id}` | Update task fields |
| DELETE | `/api/tasks/{id}` | Delete task |
| GET | `/api/notes` | List all notes (newest first) |
| POST | `/api/notes` | Create note |
| PUT | `/api/notes/{id}` | Update note |
| DELETE | `/api/notes/{id}` | Delete note |
| POST | `/api/webuntis/sync` | Open browser, user logs in, fetch timetable + messages (local only) |
| GET | `/api/schedule` | Return stored lessons + last sync timestamp |
| GET | `/api/messages` | Return stored messages + last sync timestamp |
| POST | `/api/mudo/sync` | Open browser, fetch booked Mudo sessions (local only) |
| GET | `/api/mudo/bookings` | Return stored Mudo bookings + last sync timestamp |
| POST | `/api/reminders/pull` | Pull all reminders from Apple Reminders into tasks |
| POST | `/api/apple-notes/pull` | Pull all notes from Apple Notes into notes |

WebUntis and Mudo sync endpoints return `503` when running on Render (`$RENDER` env var is set) because they require a local browser.

## Key conventions

- SQL field names are allowlisted before being interpolated into UPDATE queries (`TASK_FIELDS`, `NOTE_FIELDS`) to prevent injection.
- `get_db()` (in `db.py`) is a context manager that commits on success and closes the connection in all cases.
- INSERT statements use `RETURNING *` / `RETURNING id` to get the new row without a second SELECT.
- The WebUntis and Mudo sync endpoints are `async` but delegate to `_run_webuntis_in_thread` / `_run_mudo_in_thread` via `run_in_executor`. This runs Playwright in a dedicated thread with its own event loop.
- `_sync_executor` uses `max_workers=1` — WebUntis and Mudo syncs are serialized and cannot run concurrently.
- All other endpoints are sync.
- `done` is stored as `INTEGER` (0/1) in SQLite; the API accepts and returns a boolean.
- Task creation, update, and deletion each call the matching `reminders.py` function, so the task list and Apple Reminders stay in sync in both directions.
- Dates from WebUntis arrive as integers like `20240115` and are converted to `YYYY-MM-DD` strings.
- Times from WebUntis arrive as integers like `800` or `1345` and are formatted to `HH:MM` using `time // 100` for hours and `time % 100` for minutes.
- Apple Reminders/Notes calls (`reminders.py`) use `osascript` (AppleScript) for writes and `osascript -l JavaScript` (JXA) for reads. All calls are no-ops on non-macOS platforms and log errors without raising.

## Integration-specific details

**Apple Reminders (`reminders.py`)**
- Newly created tasks are written to a list named `"TaskBoard"` (the `LIST_NAME` constant). Change this constant to target a different list.
- `fetch_reminders()` skips any reminder whose body already contains `[task:` — this prevents re-importing reminders that were already pulled in a previous sync.
- `update_reminder()` and `delete_reminder()` search across all lists, not just `"TaskBoard"`, so reminders pulled from other lists continue to sync back correctly.

**Apple Notes (`reminders.py`)**
- `fetch_apple_notes()` reads all notes from every Notes folder via JXA. It strips HTML tags from the body to return plain text.
- Notes pulled from Apple Notes are identified by `apple_notes_id`. Re-pulling updates title/content but does not create duplicates.

**WebUntis (`webuntis.py`)**
- The school is hardcoded: `SCHOOL_URL = "https://dss.webuntis.com/WebUntis/?school=dss#/basic/login"` and `BASE_URL = "https://dss.webuntis.com"`. Update both constants if switching schools.
- Uses a **persistent browser profile** stored at `~/.local/share/taskboard/browser-profiles/webuntis` (`launch_persistent_context`). An existing valid session is reused so the user does not need to log in on every sync.
- Login detection polls the API directly every 2 seconds (up to 5 minutes) instead of relying on URL patterns — more robust across SSO redirect flows.
- The timetable fetch covers 4 weeks: current week + 3 ahead (`range(4)` in `_fetch_schedule`).
- The homework fetch window is 2 weeks back to 8 weeks ahead.
- WebUntis authenticates via a JWT stored in `localStorage.tokenString` — not cookies. All API calls include `Authorization: Bearer <token>`.

**Mudo (`mudo.py`)**
- Navigates to `BOOKINGS_URL = "https://mudo.se/mina-bokningar"` (My bookings page) — more reliable than scraping the gym schedule.
- Uses a **persistent browser profile** stored at `~/.local/share/taskboard/browser-profiles/mudo`. Once the user logs in, subsequent syncs reuse the session.
- Extracts booking details (title, date, time, duration, room, status) directly from card text without opening a dialog.
- Supports Swedish weekday names (`måndag`–`söndag`) and date strings (`"DD mon"`, `"Idag"`, `"Imorgon"`) in `_parse_date_time`.
- There is no manual Mudo sync button in the UI. The frontend auto-syncs Mudo hourly via `maybeAutoSync()`, which checks `localStorage.getItem('tb_last_autosync')` (stores the current hour) to avoid duplicate syncs within the same hour. A countdown is displayed in the Schedule tab. `autoRefresh()` re-fetches display data every hour on all deployments.

## Frontend (`static/index.html`)

**Role system** — On first load a modal asks "Who's using TaskBoard?" (`Mac` or `User`). The choice is stored in `localStorage` (`tb_role`) and can be changed from Settings. Elements with the `mac-only` CSS class are hidden in User mode (`body.role-user .mac-only { display: none }`). This controls sync buttons, Reminders pull, and Apple Notes pull — it is a UI convenience only, not a security boundary.

**Dark mode** — toggled from Settings, stored in `localStorage` (`tb_dark`). Applied via `body.dark` class which overrides CSS custom properties.

**Settings panel** — opened via the ⚙️ button in the header (far right). Contains role switcher and dark mode toggle.

## Adding features

- New API routes go in `main.py` following the existing pattern. DB access goes through `get_db()` from `db.py`.
- New frontend sections go in `static/index.html` — add a tab button, a `<div id="name-tab" class="tab">`, and matching JS functions. Notes, Schedule, and Messages tabs lazy-load on first open; follow the same pattern.
- If a new feature needs browser automation, add a new file or function to an existing `*`.py file; follow the `_run_*_in_thread` / `run_in_executor` pattern in `main.py`.
- If the feature is Mac-only (browser, osascript), add `mac-only` to its button/control so it is hidden in User mode.
- The Schedule tab displays lessons where `lesson_code != "REGULAR"` **and** all Mudo bookings. Regular lessons are intentionally hidden.
- Homework tasks synced from WebUntis are identified by a non-null `webuntis_id`. On re-sync, their `title`/`description`/`due_date` are updated but `done` is never reset.
- Tasks pulled from Apple Reminders are identified by a non-null `reminders_id`. Each pulled reminder gets a `[task:N]` tag written into its body in Reminders so future edits/completions/deletes sync back via `update_reminder` / `delete_reminder`.
