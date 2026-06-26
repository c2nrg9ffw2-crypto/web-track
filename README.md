# TaskBoard

A personal productivity web app. It tracks **tasks** and **notes**, shows a school
**timetable** fetched from WebUntis, lists booked **Mudo** training sessions, and
syncs with **Apple Reminders**.

It runs primarily as a local server on macOS, and can also deploy to the cloud on
Render with a Supabase/Postgres database.

## Features

- **Tasks** — create, edit, prioritise, due dates, mark done, delete.
- **Notes** — quick notes in a card grid with an edit modal.
- **Schedule** — week view of WebUntis timetable *changes* (cancelled / changed /
  substitution) merged with Mudo bookings.
- **Messages** — WebUntis inbox, unread first, with a notification dot.
- **Apple Reminders** — two-way sync (macOS only).
- **Roles** — pick **Mac** (full control, runs the syncs) or **User** (tasks, notes
  & views) on open.
- **Dark mode** — toggle in Settings, remembered per browser.

> The browser-automation syncs (WebUntis, Mudo) and Apple Reminders are
> **macOS/local-only** — they need a real browser and your interactive login. The
> cloud deployment serves tasks, notes, and the read-only schedule/messages views.

## Tech stack

| Layer | Tool |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| Storage | SQLite locally; Supabase/Postgres when `DATABASE_URL` is set |
| Browser automation | Playwright (Chromium, headed) |
| Apple integration | `osascript` / JXA |
| Frontend | Vanilla HTML/CSS/JS — single file `static/index.html` |
| Package manager | uv |

## Running locally

```bash
# First time only — install Chromium for Playwright (needed for the syncs):
uv run playwright install chromium

# Start the server:
uv run python main.py
```

Then open <http://localhost:8000>. Data is stored in a local SQLite file at
`~/.local/share/taskboard/data.db` (created automatically).

## Deploying to the cloud

The app can run on [Render](https://render.com) with the database on
[Supabase](https://supabase.com). Set `DATABASE_URL` to your Supabase connection
string and the app uses Postgres instead of SQLite. See **[DEPLOY.md](DEPLOY.md)**
for step-by-step instructions.

## Documentation

- **[CLAUDE.md](CLAUDE.md)** — architecture, database schema, API endpoints, conventions.
- **[INTERFACE.md](INTERFACE.md)** — frontend / UI documentation.
- **[WEBUNTIS.md](WEBUNTIS.md)** — WebUntis integration details.
- **[DEPLOY.md](DEPLOY.md)** — Render + Supabase deployment guide.
