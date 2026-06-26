import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import reminders as rem
from db import get_db, init_db, migrate_db
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

_sync_executor = ThreadPoolExecutor(max_workers=1)


def _run_mudo_in_thread():
    from mudo import sync_bookings
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(sync_bookings())
    finally:
        loop.close()


def _run_webuntis_in_thread():
    from webuntis import sync_all
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(sync_all())
    finally:
        loop.close()


TASK_FIELDS = {"title", "description", "due_date", "priority", "done"}
NOTE_FIELDS = {"title", "content"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()
    yield


app = FastAPI(lifespan=lifespan)


# --- Models ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    done: Optional[bool] = None


class NoteCreate(BaseModel):
    title: str
    content: Optional[str] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


# --- Task routes ---

@app.get("/api/tasks")
def list_tasks():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY done ASC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/tasks", status_code=201)
def create_task(task: TaskCreate):
    now = datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO tasks (title, description, due_date, priority, created_at) VALUES (?, ?, ?, ?, ?) RETURNING *",
            (task.title, task.description, task.due_date, task.priority, now),
        ).fetchone()
    rem.create_reminder(row["id"], row["title"], row["due_date"], row["description"])
    return dict(row)


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, task: TaskUpdate):
    changes = task.model_dump(exclude_none=True)
    data = {k: v for k, v in changes.items() if k in TASK_FIELDS}
    if not data:
        raise HTTPException(400, "No fields to update")
    if "done" in data:
        data["done"] = int(data["done"])
    set_clause = ", ".join(f"{k} = ?" for k in data)
    with get_db() as conn:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", (*data.values(), task_id))
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
    rem.update_reminder(
        task_id,
        title=changes.get("title"),
        due_date=changes.get("due_date"),
        done=changes.get("done"),
    )
    return dict(row)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    rem.delete_reminder(task_id)


# --- Note routes ---

@app.get("/api/notes")
def list_notes():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notes ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/notes", status_code=201)
def create_note(note: NoteCreate):
    now = datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?) RETURNING *",
            (note.title, note.content, now, now),
        ).fetchone()
        return dict(row)


@app.put("/api/notes/{note_id}")
def update_note(note_id: int, note: NoteUpdate):
    now = datetime.now().isoformat()
    data = {k: v for k, v in note.model_dump(exclude_none=True).items() if k in NOTE_FIELDS}
    data["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in data)
    with get_db() as conn:
        conn.execute(f"UPDATE notes SET {set_clause} WHERE id = ?", (*data.values(), note_id))
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Note not found")
        return dict(row)


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


# --- WebUntis routes ---

@app.post("/api/webuntis/sync")
async def webuntis_sync():
    if os.environ.get("DATABASE_URL"):
        raise HTTPException(503, "WebUntis sync is only available on local deployment")
    loop = asyncio.get_event_loop()
    lessons, homeworks, messages = await loop.run_in_executor(_sync_executor, _run_webuntis_in_thread)
    now = datetime.now().isoformat()
    new_count = updated_count = 0
    with get_db() as conn:
        conn.execute("DELETE FROM schedule_lessons")
        conn.executemany(
            "INSERT INTO schedule_lessons (date, start_time, end_time, subject, teacher, room, cancelled, lesson_code, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(l["date"], l["start_time"], l["end_time"], l["subject"], l["teacher"], l["room"], l["cancelled"], l["lesson_code"], now) for l in lessons],
        )
        for hw in homeworks:
            existing = conn.execute(
                "SELECT id FROM tasks WHERE webuntis_id = ?", (hw["webuntis_id"],)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE tasks SET title = ?, description = ?, due_date = ? WHERE webuntis_id = ?",
                    (hw["title"], hw["description"], hw["due_date"], hw["webuntis_id"]),
                )
                rem.update_reminder(existing["id"], title=hw["title"], due_date=hw["due_date"])
                updated_count += 1
            else:
                new_row = conn.execute(
                    "INSERT INTO tasks (title, description, due_date, priority, done, created_at, webuntis_id) VALUES (?, ?, ?, ?, 0, ?, ?) RETURNING id",
                    (hw["title"], hw["description"], hw["due_date"], hw["priority"], now, hw["webuntis_id"]),
                ).fetchone()
                rem.create_reminder(new_row["id"], hw["title"], hw["due_date"], hw["description"])
                new_count += 1
        conn.execute("DELETE FROM messages")
        conn.executemany(
            "INSERT INTO messages (id, subject, body, sender, sent_at, is_read, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(m["id"], m["subject"], m["body"], m["sender"], m["sent_at"], m["is_read"], now) for m in messages],
        )
    return {
        "synced_lessons": len(lessons),
        "new_homeworks": new_count,
        "updated_homeworks": updated_count,
        "synced_messages": len(messages),
    }


@app.get("/api/schedule")
def get_schedule():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM schedule_lessons ORDER BY date ASC, start_time ASC"
        ).fetchall()
        last_sync = conn.execute(
            "SELECT synced_at FROM schedule_lessons ORDER BY synced_at DESC LIMIT 1"
        ).fetchone()
        return {
            "lessons": [dict(r) for r in rows],
            "last_sync": last_sync["synced_at"] if last_sync else None,
        }


@app.get("/api/messages")
def get_messages():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY is_read ASC, sent_at DESC"
        ).fetchall()
        last_sync = conn.execute(
            "SELECT synced_at FROM messages ORDER BY synced_at DESC LIMIT 1"
        ).fetchone()
        return {
            "messages": [dict(r) for r in rows],
            "last_sync": last_sync["synced_at"] if last_sync else None,
        }


# --- Reminders pull ---

@app.post("/api/reminders/pull")
def pull_reminders():
    items = rem.fetch_reminders()
    now = datetime.now().isoformat()
    added = updated = 0
    with get_db() as conn:
        for item in items:
            apple_id = item["apple_id"]
            existing = conn.execute(
                "SELECT id FROM tasks WHERE reminders_id = ?", (apple_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE tasks SET title = ?, due_date = ? WHERE reminders_id = ?",
                    (item["name"], item["due"], apple_id),
                )
                updated += 1
            else:
                new_row = conn.execute(
                    "INSERT INTO tasks (title, description, due_date, priority, done, created_at, reminders_id) VALUES (?, ?, ?, 'medium', 0, ?, ?) RETURNING id",
                    (item["name"], item["notes"], item["due"], now, apple_id),
                ).fetchone()
                rem.tag_reminder(item["list"], item["name"], new_row["id"])
                added += 1
    return {"added": added, "updated": updated}


# --- Mudo routes ---

@app.post("/api/mudo/sync")
async def mudo_sync():
    if os.environ.get("DATABASE_URL"):
        raise HTTPException(503, "Mudo sync is only available on local deployment")
    loop = asyncio.get_event_loop()
    bookings = await loop.run_in_executor(_sync_executor, _run_mudo_in_thread)
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("DELETE FROM mudo_bookings")
        conn.executemany(
            "INSERT INTO mudo_bookings (id, date, start_time, duration_min, title, instructors, room, status, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(b["id"], b["date"], b["start_time"], b["duration_min"], b["title"], b["instructors"], b["room"], b["status"], now) for b in bookings],
        )
    return {"synced_bookings": len(bookings)}


@app.get("/api/mudo/bookings")
def get_mudo_bookings():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM mudo_bookings ORDER BY date ASC, start_time ASC"
        ).fetchall()
        last_sync = conn.execute(
            "SELECT synced_at FROM mudo_bookings ORDER BY synced_at DESC LIMIT 1"
        ).fetchone()
        return {
            "bookings": [dict(r) for r in rows],
            "last_sync": last_sync["synced_at"] if last_sync else None,
        }


# --- Frontend ---

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # No file-watch reload in the cloud (Render sets $PORT); reload locally.
    reload = "PORT" not in os.environ
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
