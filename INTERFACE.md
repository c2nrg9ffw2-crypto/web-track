# Interface Documentation

The entire frontend lives in `static/index.html` — one file containing HTML, CSS, and JavaScript with no external dependencies or build step.

## Layout

```
┌──────────────────────────────────────────────────────┐
│  TaskBoard  [Tasks] [Notes] [Schedule] [Messages 3]  │  ← sticky header
├──────────────────────────────────────────────────────┤
│                                                      │
│   Active tab content                                 │
│                                                      │
└──────────────────────────────────────────────────────┘
```

Tabs are mutually exclusive. Clicking a tab loads its content — Notes, Schedule, and Messages fetch from the API on first open.

## Tasks tab

**Adding a task**
- Type a title in the text field and press Enter, or click Add.
- Priority defaults to Medium. Can be changed to Low or High in the dropdown.
- Due date is optional (date picker).
- Description is optional (second input row).

**⟳ Reminders button**
- Pulls all non-completed reminders from every Apple Reminders list into the task list.
- First pull writes a `[task:N]` tag into each reminder's body so future edits and completions sync back.
- Re-clicking updates existing pulled tasks without creating duplicates.
- macOS only — shows an error message if the server is not running on Mac.

**Task list**
- Active tasks appear above completed ones.
- Tick the checkbox to mark done — the item greys out and the title gets a strikethrough. Marks the matching Reminders item complete on macOS.
- Click ✕ to delete. Deletes the matching Reminders item on macOS.
- Priority is shown as a colour-coded pill: green (low), yellow (medium), red (high).
- Due date is shown as a grey pill if set.
- Tasks from WebUntis homework show a purple **Homework** badge.
- Tasks pulled from Apple Reminders show a pink **Reminder** badge.

## Notes tab

**Adding a note**
- Type a title and optionally fill in the content textarea, then click Add (or press Enter in the title field).

**Note cards**
- Notes are displayed in a responsive card grid.
- Hover a card to reveal the ✕ delete button in the top-right corner.
- Click anywhere on the card to open the edit modal.

**Edit modal**
- Shows the full title and content in editable fields.
- Save: applies changes and closes.
- Cancel / click backdrop: discards changes.
- Delete button (bottom-left): deletes the note after a confirmation prompt.

## Schedule tab

**Sync buttons**
- **Sync WebUntis** — opens a browser window, user logs in, fetches timetable changes and messages. Also syncs homework to the Tasks tab.
- **Sync Mudo** (green) — opens a browser window, user logs in to mudo.se, fetches booked training sessions.
- Both buttons disable while running and show status text. Last sync times for each source are shown next to the buttons.

**Week view**
- Shows one week at a time: Mon–Sun, only days that have items.
- ← Prev / Next → buttons navigate between weeks.
- **WebUntis changes** — lessons that deviate from the normal schedule. Regular lessons are hidden. Each shows: time range, subject, teacher, room, and a badge (Cancelled / Changed / Substitution / Free period).
- **Mudo bookings** — training sessions where the user is booked. Green left border. Shows: start time, duration, class title, instructor, room, and a green **Booked** or yellow **Waitlist** badge.
- Items on the same day are sorted by start time.
- If a week has no changes or bookings, shows "No changes or bookings this week."

## Messages tab

- Lists WebUntis inbox messages, unread first.
- The tab button shows an unread count badge (e.g. **Messages 3**).
- Unread messages have a blue left border and bold subject.
- Click a message card to expand the full body (HTML is stripped to plain text).
- Messages are populated by the WebUntis sync — there is no separate Messages sync button.

## Styling

CSS custom properties (variables) control the colour scheme, defined in `:root`:

| Variable | Purpose |
|---|---|
| `--bg` | Page background (`#f1f5f9`) |
| `--surface` | Card/modal background (`#ffffff`) |
| `--border` | Border colour (`#e2e8f0`) |
| `--text` | Main text (`#1e293b`) |
| `--muted` | Secondary text (`#64748b`) |
| `--primary` | Accent / buttons (`#4f46e5` indigo) |
| `--radius` | Border radius for cards (`10px`) |

To change the colour scheme, update these variables at the top of the `<style>` block.

## JavaScript structure

All JS is at the bottom of `static/index.html` inside a single `<script>` tag.

| Function(s) | Responsibility |
|---|---|
| `showTab(name)` | Switch active tab, trigger lazy load |
| `loadTasks()`, `addTask()`, `toggleTask()`, `deleteTask()` | Task CRUD |
| `syncReminders()` | Pull all Apple Reminders into the task list |
| `loadNotes()`, `addNote()`, `openModal()`, `saveNote()`, `deleteNote()`, `deleteNoteModal()`, `closeModal()` | Notes CRUD + modal |
| `loadSchedule()`, `renderSchedule()`, `changeWeek()` | Schedule display (merges WebUntis + Mudo) |
| `syncWebUntis()`, `syncMudo()` | Trigger sync and refresh schedule/tasks/messages |
| `loadMessages()`, `toggleMsg()`, `stripHtml()` | Messages display |
| `api(method, url, body)` | Shared fetch wrapper — handles JSON and 204 responses |
| `esc(s)` | HTML-escape strings before inserting into innerHTML |
| `val(id)` | Get trimmed value of an input by id |
| `clear(...ids)` | Reset input fields |
| `fmtDate(iso)` | Format ISO datetime string for display |

## State held in JS

| Variable | Content |
|---|---|
| `notesCache` | `{id: note}` map — populated by `loadNotes()`, used by `openModal()` to avoid re-fetching |
| `currentNoteId` | ID of the note currently open in the modal |
| `weekOffset` | Number of weeks from current week shown in Schedule (0 = this week) |
| `allLessons` | All lessons returned from `/api/schedule`, filtered to non-REGULAR by `renderSchedule()` |
| `mudoBookings` | All bookings returned from `/api/mudo/bookings`, merged into schedule view |
| `lastSync` | ISO timestamp of the last WebUntis sync |
