# Interface Documentation

The entire frontend lives in `static/index.html` — one file containing HTML, CSS, and JavaScript with no external dependencies or build step.

## Layout

```
┌─────────────────────────────────────────┐
│  TaskBoard   [Tasks] [Notes] [Schedule] │  ← sticky header
├─────────────────────────────────────────┤
│                                         │
│   Active tab content                    │
│                                         │
└─────────────────────────────────────────┘
```

Tabs are mutually exclusive. Clicking a tab loads its content — Notes and Schedule fetch from the API on first open.

## Tasks tab

**Adding a task**
- Type a title in the text field and press Enter, or click Add.
- Priority defaults to Medium. Can be changed to Low or High in the dropdown.
- Due date is optional (date picker).
- Description is optional (second input row).

**Task list**
- Active tasks appear above completed ones.
- Tick the checkbox to mark done — the item greys out and the title gets a strikethrough.
- Click ✕ to delete.
- Priority is shown as a colour-coded pill: green (low), yellow (medium), red (high).
- Due date is shown as a grey pill if set.

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

**Sync button**
- Click "Sync WebUntis" to fetch a fresh timetable (see `WEBUNTIS.md` for what happens).
- The button disables and shows status text while the sync is running.
- Last sync time is shown next to the button once data exists.

**Week view**
- Shows one week at a time: Mon–Sun, only days that have lessons.
- ← Prev / Next → buttons navigate between weeks.
- Each lesson shows: time range, subject name, teacher, room.
- Cancelled lessons are shown at 45% opacity with a red "Cancelled" badge.

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
| `loadNotes()`, `addNote()`, `openModal()`, `saveNote()`, `deleteNote()`, `deleteNoteModal()`, `closeModal()` | Notes CRUD + modal |
| `loadSchedule()`, `renderSchedule()`, `changeWeek()`, `syncWebUntis()` | Schedule display and sync |
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
| `allLessons` | All lessons returned from `/api/schedule`, filtered by `renderSchedule()` |
| `lastSync` | ISO timestamp of the last WebUntis sync |
