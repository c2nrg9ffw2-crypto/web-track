# Interface Documentation

The entire frontend lives in `static/index.html` — one file containing HTML, CSS, and JavaScript with no external dependencies or build step.

## Layout

```
┌────────────────────────────────────────────────────────────────┐
│  TaskBoard  [Tasks] [Notes] [Schedule] [Messages •3]      [⚙️]  │  ← sticky header
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   Active tab content                                           │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

Tabs are mutually exclusive. Clicking a tab loads its content — Notes, Schedule, and Messages fetch from the API on first open. The **⚙️ Settings** button sits at the far right of the header.

## First open — role chooser

On first load a modal asks **"Who's using TaskBoard?"** with two choices:

- **🖥️ Mac** — full control. Shows the local-only sync controls (⟳ Reminders, Sync WebUntis, Sync Mudo). Pick this when running locally on macOS.
- **👤 User** — Tasks, Notes, and read-only Schedule/Messages. The sync controls are hidden. This is the right choice for the cloud (Render) deployment.

The choice is stored in `localStorage` (`tb_role`) so it is only asked once per browser. It can be changed any time from **Settings → Role**. Hiding the sync controls in User mode is a UI convenience only — the API endpoints still exist; it is not a security boundary.

**Auto-sync (Mac role only).** Choosing Mac runs all syncs (WebUntis → Mudo → Reminders) immediately, and they re-run automatically once at the start of each day the app is open. The last auto-sync date is stored in `localStorage` (`tb_last_autosync`); on load and every 15 minutes the app compares it to today's local date and re-syncs if it is a new day. Because the WebUntis/Mudo syncs open a login browser window, this only makes sense — and only runs — in the Mac role. See `autoSync()` / `maybeAutoSync()`.

## Tasks tab

**Adding a task**
- Type a title in the text field and press Enter, or click Add.
- Priority defaults to Medium. Can be changed to Low or High in the dropdown.
- Due date is optional (date picker).
- Description is optional (second input row).

**⟳ Reminders button** (Mac role only — hidden in User role)
- Pulls all non-completed reminders from every Apple Reminders list into the task list.
- First pull writes a `[task:N]` tag into each reminder's body so future edits and completions sync back.
- Re-clicking updates existing pulled tasks without creating duplicates.
- macOS only — shows an error message if the server is not running on Mac.

**Editing a task**
- **Long-press** (press and hold ~0.5s) on a task's text to open the edit modal — title, description, priority, and due date. Save persists via `PUT /api/tasks/{id}`; clearing the description or due date removes them.
- The Delete button in the modal removes the task.
- A short tap/click does nothing; the checkbox (done) and ✕ (delete) remain direct actions and are excluded from the long-press.

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

**Sync buttons** (Mac role only — hidden in User role)
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
- The tab button shows a small **red dot** plus an unread count badge (e.g. **Messages •3**) whenever at least one message is unread. The unread state is fetched on page load (via `refreshUnread()`), so the dot appears without opening the tab.
- Unread messages have a blue left border and bold subject.
- Click a message card to expand the full body (HTML is stripped to plain text).
- Messages are populated by the WebUntis sync — there is no separate Messages sync button.

## Settings tab (⚙️)

Opened from the gear button on the right of the header. Available in both roles.

- **Appearance → Dark mode** — a toggle switch. Persisted in `localStorage` (`tb_dark`) and re-applied on every load. It works by adding a `dark` class to `<body>`, which overrides the colour-scheme CSS variables.
- **Role** — shows the current role (Mac / User) and a **Switch role** button that reopens the role chooser.

## Styling

CSS custom properties (variables) control the colour scheme, defined in `:root`:

| Variable | Purpose |
|---|---|
| `--bg` | Page background (`#f1f5f9`) |
| `--surface` | Card/modal background (`#ffffff`) |
| `--surface-alt` | Tinted surface, e.g. unread message cards (`#f8f7ff`) |
| `--border` | Border colour (`#e2e8f0`) |
| `--text` | Main text (`#1e293b`) |
| `--muted` | Secondary text (`#64748b`) |
| `--primary` | Accent / buttons (`#4f46e5` indigo) |
| `--primary-h` | Accent hover (`#4338ca`) |
| `--hover` | Ghost-button / generic hover (`#cbd5e1`) |
| `--radius` | Border radius for cards (`10px`) |

To change the colour scheme, update these variables at the top of the `<style>` block.

**Dark mode** is implemented as a single `body.dark { … }` rule that re-defines the same variables with a dark palette. Because every component reads the variables (no hardcoded colours), adding `dark` to `<body>` re-themes the whole UI. New colours should be added as variables, not literals, so they theme automatically.

## JavaScript structure

All JS is at the bottom of `static/index.html` inside a single `<script>` tag.

| Function(s) | Responsibility |
|---|---|
| `showTab(name)` | Switch active tab, trigger lazy load |
| `getRole()`, `setRole()`, `applyRole()`, `initRole()`, `openRoleChooser()` | Role (Mac/User) state — toggles `body.role-user`, persists `tb_role` |
| `autoSync()`, `maybeAutoSync(force)` | Mac role: run all syncs on selection and once per day (`tb_last_autosync`) |
| `getDark()`, `setDark()`, `applyDark()` | Dark-mode state — toggles `body.dark`, persists `tb_dark` |
| `loadTasks()`, `addTask()`, `toggleTask()`, `deleteTask()` | Task CRUD (caches into `tasksCache`) |
| `openTaskModal()`, `closeTaskModal()`, `saveTaskModal()`, `deleteTaskModal()` | Task edit modal (opened by long-press) |
| `syncReminders()` | Pull all Apple Reminders into the task list |
| `loadNotes()`, `addNote()`, `openModal()`, `saveNote()`, `deleteNote()`, `deleteNoteModal()`, `closeModal()` | Notes CRUD + modal |
| `loadSchedule()`, `renderSchedule()`, `changeWeek()` | Schedule display (merges WebUntis + Mudo) |
| `syncWebUntis()`, `syncMudo()` | Trigger sync and refresh schedule/tasks/messages |
| `fetchMessages()` | GET `/api/messages`, refresh unread indicator, return the list (shared by the two below) |
| `loadMessages()`, `toggleMsg()`, `stripHtml()` | Messages display |
| `setUnread(n)`, `refreshUnread()` | Drive the unread dot + count badge; `refreshUnread()` runs on load |
| `api(method, url, body)` | Shared fetch wrapper — handles JSON and 204 responses |
| `esc(s)` | HTML-escape strings before inserting into innerHTML |
| `val(id)` | Get trimmed value of an input by id |
| `clear(...ids)` | Reset input fields |
| `fmtDate(iso)` | Format ISO datetime string for display |

On load the script runs `applyDark()`, `initRole()`, `loadTasks()`, and `refreshUnread()`.

## Persisted preferences (localStorage)

| Key | Values | Set by |
|---|---|---|
| `tb_role` | `mac` / `user` | role chooser |
| `tb_dark` | `1` / `0` | dark-mode toggle |
| `tb_last_autosync` | local `YYYY-MM-DD` | last day auto-sync ran (Mac role) |

## State held in JS

| Variable | Content |
|---|---|
| `notesCache` | `{id: note}` map — populated by `loadNotes()`, used by `openModal()` to avoid re-fetching |
| `currentNoteId` | ID of the note currently open in the modal |
| `tasksCache` | `{id: task}` map — populated by `loadTasks()`, used by `openTaskModal()` |
| `currentTaskId` | ID of the task currently open in the edit modal |
| `weekOffset` | Number of weeks from current week shown in Schedule (0 = this week) |
| `allLessons` | All lessons returned from `/api/schedule`, filtered to non-REGULAR by `renderSchedule()` |
| `mudoBookings` | All bookings returned from `/api/mudo/bookings`, merged into schedule view |
| `lastSync` | ISO timestamp of the last WebUntis sync |
