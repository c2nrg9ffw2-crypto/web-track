# Deploying to Render + Supabase

This app can run in the cloud on [Render](https://render.com) with its database
hosted on [Supabase](https://supabase.com) (Postgres).

## What runs in the cloud vs. only locally

| Feature | Cloud (Render) | Local (your Mac) |
|---|---|---|
| Tasks (create/edit/delete) | ✅ | ✅ |
| Notes | ✅ | ✅ |
| Viewing synced Schedule / Messages / Mudo | ✅ (read-only) | ✅ |
| **WebUntis sync** | ❌ needs a real browser + your login | ✅ |
| **Mudo sync** | ❌ needs a real browser + your login | ✅ |
| **Apple Reminders** | ❌ macOS-only | ✅ |

WebUntis/Mudo/Reminders are **not fixed yet** — that's planned for later. For now
you run those syncs from your Mac, pointed at the same Supabase database, so the
data they produce shows up in the cloud app.

## How the database is chosen

`db.py` checks the `DATABASE_URL` environment variable:

- **Set** → uses Supabase / Postgres.
- **Unset** → uses a local SQLite file at `~/.local/share/taskboard/data.db`.

Tables are created automatically on startup (`init_db()` + `migrate_db()`), so
there's no manual SQL to run.

## 1. Create the Supabase database

1. Create a project at https://supabase.com.
2. Go to **Project Settings → Database → Connection string → URI**.
3. Copy the connection string. Prefer the **Connection pooler** (Transaction)
   string — it looks like:
   ```
   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```
   Replace `<password>` with your database password.

## 2. Deploy on Render

This repo includes `render.yaml`, so you can deploy as a Blueprint:

1. Push this repo to GitHub (already done as `web-track`).
2. In Render: **New → Blueprint**, pick the `web-track` repo.
3. When prompted, set the `DATABASE_URL` env var to the Supabase URI from step 1.
4. Deploy. Render runs:
   - build: `pip install -r requirements.txt`
   - start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Or configure a Web Service manually with those same commands and env var.

## 3. (Optional) Run sync locally into Supabase

To make local WebUntis/Mudo/Reminders syncs write to Supabase instead of your
local SQLite, export the same connection string before starting the app:

```bash
export DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres"
uv run python main.py
```

Sync from there, and the results appear in the cloud app.
