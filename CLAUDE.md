# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A personal productivity web app that runs as a local server on macOS. It tracks tasks, notes, a school timetable fetched from WebUntis, booked Mudo training sessions, and syncs with Apple Reminders. The user opens it in a browser at `http://localhost:8000`.

## Tech stack

| Layer | Tool |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| Storage | SQLite at `~/.local/share/taskboard/data.db` locally; Supabase/Postgres when `DATABASE_URL` is set (see `db.py`) |
| Browser automation | Playwright (Chromium, headed) |
| Apple integration | `osascript` / JXA — no extra packages needed |
| Frontend | Vanilla HTML/CSS/JS — single file `static/index.html` |
| Package manager | uv |

## File structure

```
main.py              # FastAPI app — all routes and models
db.py                # DB layer — SQLite locally or Supabase/Postgres via DATABASE_URL
webuntis.py          # Playwright automation for syncing the timetable + messages
mudo.py              # Playwright automation for syncing Mudo.se training bookings
reminders.py         # Apple Reminders integration via osascript / JXA
static/index.html    # Entire frontend (HTML + CSS + JS in one file)
pyproject.toml       # Dependencies and project metadata
requirements.txt     # Cloud (Render) dependencies — no Playwright
render.yaml          # Render Blueprint (build/start commands, env vars)
INTERFACE.md         # Frontend / UI documentation
WEBUNTIS.md          # WebUntis integration documentation
DEPLOY.md            # Render + Supabase deployment guide
```

Data is stored outside the project directory in `~/.local/share/taskboard/data.db` so it is never accidentally committed.

## How to run

```bash
# First time only — install Chromium for Playwright:
uv run playwright install chromium

# Start the server:
uv run python main.py
```

Server listens on `0.0.0.0:8000` with hot-reload enabled.

## Database schema

Five tables, all created automatically on first run by `init_db()`.

**tasks**
- `id`, `title`, `description`, `due_date` (YYYY-MM-DD), `priority` (low/medium/high), `done` (0/1), `created_at`
- `webuntis_id` (nullable — set for homework tasks synced from WebUntis, e.g. `"hw_123"`)
- `reminders_id` (nullable — set for tasks pulled from Apple Reminders; stores the Apple reminder's UUID)

**notes**
- `id`, `title`, `content`, `created_at`, `updated_at`

**schedule_lessons**
- `id`, `date` (YYYY-MM-DD), `start_time` (HH:MM), `end_time` (HH:MM), `subject`, `teacher`, `room`, `cancelled` (0/1), `lesson_code` (REGULAR/CANCELLED/IRREGULAR/SUBSTITUTION/FREE), `synced_at`

**messages**
- `id` (WebUntis message ID, primary key), `subject`, `body` (HTML), `sender`, `sent_at`, `is_read` (0/1), `synced_at`

**mudo_bookings**
- `id` (TEXT, `"YYYY-MM-DD_HH:MM_title"` composite key), `date` (YYYY-MM-DD), `start_time` (HH:MM), `duration_min` (INTEGER, nullable), `title`, `instructors` (comma-separated), `room`, `status` (`booked` or `waitlist`), `synced_at`

### Adding new DB columns

New columns go in `init_db()` **and** as an `ALTER TABLE` statement inside `migrate_db()` (both in `db.py`). `migrate_db()` is safe to re-run: on Postgres it uses `ADD COLUMN IF NOT EXISTS`, on SQLite it catches and ignores the "column already exists" error. Both functions are called on startup via the `lifespan` handler.

### SQLite vs. Postgres

`db.py` picks the backend from `DATABASE_URL` (Postgres when set, else SQLite) and exposes a `get_db()` wrapper that translates `?` placeholders to `%s` for Postgres. Write SQL with `?` placeholders. For inserts that need the new row, use `RETURNING *` / `RETURNING id` and `.fetchone()` (works on both backends) rather than `cursor.lastrowid` (SQLite-only). See `DEPLOY.md` for Render + Supabase setup.

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
| POST | `/api/webuntis/sync` | Open browser, user logs in, fetch timetable + messages |
| GET | `/api/schedule` | Return stored lessons + last sync timestamp |
| GET | `/api/messages` | Return stored messages + last sync timestamp |
| POST | `/api/mudo/sync` | Open browser, user logs in to Mudo, fetch booked sessions |
| GET | `/api/mudo/bookings` | Return stored Mudo bookings + last sync timestamp |
| POST | `/api/reminders/pull` | Pull all reminders from Apple Reminders into tasks |

## Key conventions

- SQL field names are allowlisted before being interpolated into UPDATE queries (`TASK_FIELDS`, `NOTE_FIELDS`) to prevent injection.
- `get_db()` is a context manager that commits on success and closes the connection in all cases.
- The WebUntis and Mudo sync endpoints are `async` but delegate to `_run_webuntis_in_thread` / `_run_mudo_in_thread` via `run_in_executor`. This runs Playwright in a dedicated thread with its own event loop — necessary on Windows (uvicorn's `SelectorEventLoop` can't spawn subprocesses) and harmless on macOS (the primary platform).
- All other endpoints are sync.
- `done` is stored as `INTEGER` (0/1) in SQLite; the API accepts and returns a boolean.
- Dates from WebUntis arrive as integers like `20240115` and are converted to `YYYY-MM-DD` strings.
- Times from WebUntis arrive as integers like `800` or `1345` and are formatted to `HH:MM` using `time // 100` for hours and `time % 100` for minutes.
- Apple Reminders calls (`reminders.py`) use `osascript` (AppleScript) for writes and `osascript -l JavaScript` (JXA) for reads. All calls are no-ops on non-macOS platforms and log errors without raising.

## Adding features

- New API routes go in `main.py` following the existing pattern.
- New frontend sections go in `static/index.html` — add a tab button, a `<div id="name-tab" class="tab">`, and matching JS functions. Notes and Schedule tabs lazy-load on first open; follow the same pattern.
- If a new feature needs browser automation, add a new file (e.g. `mudo.py`) or a function to `webuntis.py`; follow the `_run_webuntis_in_thread` / `_run_mudo_in_thread` thread-executor pattern in `main.py`.
- The Schedule tab displays lessons where `lesson_code != "REGULAR"` **and** all Mudo bookings. Regular lessons are intentionally hidden.
- Homework tasks synced from WebUntis are identified by a non-null `webuntis_id`. On re-sync, their `title`/`description`/`due_date` are updated but `done` is never reset.
- Tasks pulled from Apple Reminders are identified by a non-null `reminders_id`. Each pulled reminder gets a `[task:N]` tag written into its body in Reminders so future edits/completions/deletes sync back via `update_reminder` / `delete_reminder`.
