import json
import subprocess
import sys

LIST_NAME = "TaskBoard"


def _run(script: str) -> str:
    if sys.platform != "darwin":
        return ""
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0 and r.stderr:
            print(f"Reminders error: {r.stderr.strip()}")
        return r.stdout.strip()
    except Exception as e:
        print(f"Reminders: osascript failed: {e}")
        return ""


def _run_js(script: str) -> str:
    if sys.platform != "darwin":
        return ""
    try:
        r = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0 and r.stderr:
            print(f"Reminders JS error: {r.stderr.strip()}")
        return r.stdout.strip()
    except Exception as e:
        print(f"Reminders: osascript JS failed: {e}")
        return ""


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _tag(task_id: int) -> str:
    # Wrapped in brackets so "[task:4]" is never a substring of "[task:42]"
    return f"[task:{task_id}]"


def _date_lines(iso: str) -> str:
    y, m, d = iso.split("-")
    return (
        f"set dueDate to current date\n"
        f"    set year of dueDate to {y}\n"
        f"    set month of dueDate to {int(m)}\n"
        f"    set day of dueDate to {int(d)}\n"
        f"    set hours of dueDate to 23\n"
        f"    set minutes of dueDate to 59\n"
        f"    set seconds of dueDate to 0"
    )


def fetch_reminders() -> list[dict]:
    """Read all non-completed, untagged reminders from every Reminders list."""
    script = """
const app = Application('Reminders');
const results = [];
for (const list of app.lists()) {
    const listName = list.name();
    for (const r of list.reminders.whose({completed: false})()) {
        const body = r.body() || '';
        if (body.includes('[task:')) continue;
        const due = r.dueDate();
        results.push({
            apple_id: r.id(),
            name: r.name(),
            due: due ? due.toISOString().slice(0, 10) : null,
            list: listName,
            notes: body || null,
        });
    }
}
JSON.stringify(results);
"""
    output = _run_js(script)
    try:
        return json.loads(output) if output else []
    except Exception as e:
        print(f"Reminders: could not parse fetch output: {e}")
        return []


def tag_reminder(list_name: str, reminder_name: str, task_id: int):
    """Add [task:N] to an existing reminder's body so future edits sync back."""
    script = f"""tell application "Reminders"
    if not (exists list "{_esc(list_name)}") then return
    set found to (reminders of list "{_esc(list_name)}") whose name is "{_esc(reminder_name)}" and completed is false
    if (count of found) > 0 then
        set r to item 1 of found
        set body of r to "{_tag(task_id)}" & return & body of r
    end if
end tell"""
    _run(script)


def create_reminder(task_id: int, title: str, due_date: str | None = None, notes: str | None = None):
    body = _tag(task_id)
    if notes:
        body += f"\\n{_esc(notes)}"

    if due_date:
        script = f"""tell application "Reminders"
    if not (exists list "{LIST_NAME}") then make new list with properties {{name:"{LIST_NAME}"}}
    {_date_lines(due_date)}
    make new reminder at list "{LIST_NAME}" with properties {{name:"{_esc(title)}", body:"{body}", due date:dueDate}}
end tell"""
    else:
        script = f"""tell application "Reminders"
    if not (exists list "{LIST_NAME}") then make new list with properties {{name:"{LIST_NAME}"}}
    make new reminder at list "{LIST_NAME}" with properties {{name:"{_esc(title)}", body:"{body}"}}
end tell"""
    _run(script)


def update_reminder(task_id: int, title: str | None = None, due_date: str | None = None, done: bool | None = None):
    sets = []
    if title is not None:
        sets.append(f'set name of r to "{_esc(title)}"')
    if due_date is not None:
        sets.append("set due date of r to dueDate")
    if done is not None:
        sets.append(f'set completed of r to {"true" if done else "false"}')
    if not sets:
        return

    date_block = f"    {_date_lines(due_date)}\n" if due_date else ""
    set_block = "\n        ".join(sets)
    tag = _tag(task_id)

    # Search all lists so pulled reminders (outside TaskBoard) also sync
    script = f"""tell application "Reminders"
{date_block}    set found to {{}}
    repeat with l in lists
        set found to found & (reminders of l whose body contains "{tag}")
    end repeat
    if (count of found) > 0 then
        set r to item 1 of found
        {set_block}
    end if
end tell"""
    _run(script)


def delete_reminder(task_id: int):
    tag = _tag(task_id)
    script = f"""tell application "Reminders"
    set found to {{}}
    repeat with l in lists
        set found to found & (reminders of l whose body contains "{tag}")
    end repeat
    repeat with r in found
        delete r
    end repeat
end tell"""
    _run(script)
