# WebUntis Integration

## School details

| Field | Value |
|---|---|
| School name | DSS |
| Login URL | `https://dss.webuntis.com/WebUntis/?school=dss#/basic/login` |
| API base | `https://dss.webuntis.com` |

## How the sync works

All logic lives in `webuntis.py`, triggered by `POST /api/webuntis/sync` in `main.py`.

### Step-by-step

1. **Open browser** — Playwright launches a visible (headed) Chromium window using a **persistent profile** (`launch_persistent_context`) stored at `~/.local/share/taskboard/browser-profiles/webuntis`, and navigates to the DSS WebUntis login page. Because the profile persists cookies and localStorage between runs, an existing valid session is reused and login is skipped.
2. **User logs in (if needed)** — If the session has expired, the app waits up to 5 minutes for the page to be back on `webuntis.com` with no `login` in the URL hash. This handles Office 365 SSO redirects, which temporarily leave the webuntis.com domain. With a valid persisted session this step passes immediately.
3. **Read session** — Waits for the network to go idle (`networkidle`), then a 2-second pause to let the session fully settle.
4. **Get user identity** — Reads the JWT from `localStorage.tokenString` (WebUntis stores auth tokens in localStorage, not cookies). Calls `GET /WebUntis/api/rest/view/v1/app/data` with `Authorization: Bearer <token>`. Extracts `elemId` (student ID) and `elemType` from the response.
5. **Fetch timetable** — Calls `GET /WebUntis/api/public/timetable/weekly/data` four times: current week + 3 weeks ahead. Each call uses `elementType`, `elementId`, `date` (Monday of the week), and `formatId=1`.
6. **Close browser** — Playwright closes Chromium once all data is fetched.
7. **Parse lessons** — Raw period objects are converted to clean lesson dicts (see data format below).
8. **Store** — `main.py` wipes `schedule_lessons` and inserts the fresh data with a `synced_at` timestamp.

### API endpoints used

| Endpoint | Purpose |
|---|---|
| `GET /WebUntis/api/rest/view/v1/app/data` | Get logged-in user's `elemId` and `elemType` |
| `GET /WebUntis/api/public/timetable/weekly/data` | Fetch one week of timetable periods |
| `GET /WebUntis/api/homeworks/lessons` | Fetch homework assignments |
| `GET /WebUntis/api/rest/view/v1/messages` | Fetch inbox messages |

## Message sync

Messages are fetched from `/WebUntis/api/rest/view/v1/messages` in the same session as the schedule. The full inbox is replaced on every sync. Each message is stored in the `messages` table with:
- `id`: WebUntis message ID (used as primary key — no duplicates)
- `subject`, `body` (HTML stripped on display), `sender`, `sent_at`
- `is_read`: from WebUntis — reflects actual read status, reset each sync

Unread messages appear with a blue left border and bold subject in the Messages tab. The tab button shows an unread count badge. Clicking a message card expands the full body.

## Homework sync

Homework is fetched in the same browser session as the schedule, immediately after. The date range is 2 weeks back to 8 weeks ahead to catch overdue homework.

Each homework entry is saved as a **task** in the `tasks` table with:
- `title`: `"Subject: homework text…"` (truncated to 80 chars)
- `description`: full homework text
- `due_date`: from WebUntis `dueDate` field
- `priority`: medium
- `webuntis_id`: `"hw_<id>"` — used to detect duplicates

On each sync: new homeworks are inserted, existing ones (matched by `webuntis_id`) have their title/description/due_date updated in case the teacher edited them. The `done` status is **never** reset — completing a homework task in the app survives re-syncs.

Homework tasks show a purple "Homework" badge in the Tasks tab.

All API calls (`app/data`, timetable, homeworks) are made with `page.request.get()` and include an `Authorization: Bearer <token>` header sourced from `localStorage.tokenString`. WebUntis uses JWT-based auth rather than cookies, so the header is required.

## Raw data format from WebUntis

### Timetable response structure

```
data.result.data
├── elementPeriods          # dict keyed by element ID
│   └── "<elemId>": [...]   # list of period objects
└── elements                # lookup list for subjects, teachers, rooms
```

### Period object (one lesson)

```json
{
  "lessonId": 12345,
  "date": 20240115,
  "startTime": 800,
  "endTime": 850,
  "lessonCode": "REGULAR",
  "is": { "cancelled": false, "regular": true },
  "elements": [
    { "type": 1, "id": 11111 },
    { "type": 2, "id": 22222 },
    { "type": 3, "id": 33333 },
    { "type": 4, "id": 44444 }
  ]
}
```

### Element type codes

| Type | Meaning |
|---|---|
| 1 | Student / class |
| 2 | Teacher |
| 3 | Subject |
| 4 | Room |

### Time and date encoding

- **Date**: integer `YYYYMMDD` → converted to string `YYYY-MM-DD`
- **Time**: integer where `800` = 08:00 and `1345` = 13:45 → converted to `HH:MM` using `time // 100` for hours and `time % 100` for minutes

### Cancelled lesson detection

A lesson is marked cancelled if either:
- `period["lessonCode"] == "CANCELLED"`, or
- `period["is"]["cancelled"] == True`

## Stored lesson format

After parsing, each lesson stored in `schedule_lessons` looks like:

```python
{
    "date": "2024-01-15",       # YYYY-MM-DD
    "start_time": "08:00",      # HH:MM
    "end_time": "08:50",        # HH:MM
    "subject": "MAT",           # short name from elements list
    "teacher": "Smith",         # short name from elements list
    "room": "101",              # short name from elements list
    "cancelled": 0,             # 0 or 1
    "lesson_code": "CANCELLED"  # raw code from WebUntis
}
```

All lessons (regular and changed) are stored. Each sync replaces all stored lessons (full replace, not incremental).

## What counts as a change

The Schedule tab only displays lessons where `lesson_code != "REGULAR"`. Known codes:

| Code | Display badge | Meaning |
|---|---|---|
| `REGULAR` | — (hidden) | Normal lesson, not shown |
| `CANCELLED` | Cancelled (red) | Lesson is cancelled |
| `IRREGULAR` | Changed (yellow) | Lesson has a change (different teacher, room, etc.) |
| `SUBSTITUTION` | Substitution (blue) | A substitute teacher is covering |
| `FREE` | Free period (red) | Free period instead of a lesson |

If a week has no changes, the view shows "No changes this week."

## Troubleshooting

**Browser opens but closes before I can log in**
The timeout is 5 minutes (`300_000` ms in `webuntis.py`). If you need more time, increase `timeout=300_000`.

**Sync completes but shows 0 lessons**
The API response structure may differ slightly for this school. Add a `print(data)` after `data = await r.json()` in `webuntis.py` to inspect the raw response and adjust the key path (`data → result → data → elementPeriods`).

**"elemId" KeyError**
The user object path in the app data response might differ. Print `app_data` after the first API call to find the correct path.

**Adding more weeks**
Change `range(4)` in `webuntis.py` to `range(N)` for N weeks ahead.

## One-time setup (macOS)

Before the first sync, install the Chromium browser that Playwright uses:

```bash
uv run playwright install chromium
```

This only needs to be done once per machine. The server is designed to run on macOS. Windows works for local testing but is not the primary target.
