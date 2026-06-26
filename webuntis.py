from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

SCHOOL_URL = "https://dss.webuntis.com/WebUntis/?school=dss#/basic/login"
BASE_URL = "https://dss.webuntis.com"

# Persistent browser profile so the WebUntis session (token in localStorage)
# survives between runs — avoids logging in on every sync.
PROFILE_DIR = Path.home() / ".local" / "share" / "taskboard" / "browser-profiles" / "webuntis"


async def sync_all() -> tuple[list[dict], list[dict], list[dict]]:
    """Open a browser, wait for login, then fetch schedule and homeworks."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto(SCHOOL_URL)
        await page.wait_for_function(
            "() => window.location.hostname.includes('webuntis.com') && !window.location.hash.includes('login')",
            timeout=300_000,
        )
        await page.wait_for_load_state("networkidle", timeout=30_000)
        await page.wait_for_timeout(2000)

        # WebUntis authenticates API calls with a JWT stored in localStorage,
        # not cookies — page.request.get() needs this header to work.
        token = await page.evaluate("() => localStorage.getItem('tokenString')")
        auth = {"Authorization": f"Bearer {token}"} if token else {}

        r = await page.request.get(f"{BASE_URL}/WebUntis/api/rest/view/v1/app/data", headers=auth)
        app_data = await r.json()
        user = app_data["data"]["user"]
        elem_id = user["elemId"]
        elem_type = user["elemType"]

        lessons = await _fetch_schedule(page, elem_id, elem_type, auth)
        homeworks = await _fetch_homeworks(page, auth)
        messages = await _fetch_messages(page, auth)

        await ctx.close()

    return lessons, homeworks, messages


async def _fetch_schedule(page, elem_id: int, elem_type: int, auth: dict) -> list[dict]:
    today = datetime.today()
    monday = today - timedelta(days=today.weekday())

    all_periods: list[dict] = []
    elements_map: dict[tuple, dict] = {}
    seen: set[tuple] = set()

    for week in range(4):
        date = monday + timedelta(weeks=week)
        r = await page.request.get(
            f"{BASE_URL}/WebUntis/api/public/timetable/weekly/data",
            params={
                "elementType": elem_type,
                "elementId": elem_id,
                "date": date.strftime("%Y-%m-%d"),
                "formatId": 1,
            },
            headers=auth,
        )
        data = await r.json()
        result = data.get("data", {}).get("result", {}).get("data", {})

        for el in result.get("elements", []):
            elements_map[(el["type"], el["id"])] = el

        for periods in result.get("elementPeriods", {}).values():
            for period in periods:
                key = (period.get("lessonId"), period["date"], period["startTime"])
                if key in seen:
                    continue
                seen.add(key)
                all_periods.append(period)

    lessons = []
    for period in all_periods:
        raw_date = str(period["date"])
        date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"

        start = period["startTime"]
        end = period["endTime"]
        start_fmt = f"{start // 100:02d}:{start % 100:02d}"
        end_fmt = f"{end // 100:02d}:{end % 100:02d}"

        subject = teacher = room = None
        for el in period.get("elements", []):
            info = elements_map.get((el["type"], el["id"]), {})
            if el["type"] == 3:
                subject = info.get("name")
            elif el["type"] == 2:
                teacher = info.get("name")
            elif el["type"] == 4:
                room = info.get("name")

        lesson_code = period.get("lessonCode") or "REGULAR"
        is_data = period.get("is", {})
        cancelled = lesson_code == "CANCELLED" or is_data.get("cancelled", False)

        lessons.append({
            "date": date_str,
            "start_time": start_fmt,
            "end_time": end_fmt,
            "subject": subject,
            "teacher": teacher,
            "room": room,
            "cancelled": int(cancelled),
            "lesson_code": lesson_code,
        })

    lessons.sort(key=lambda x: (x["date"], x["start_time"]))
    return lessons


async def _fetch_homeworks(page, auth: dict) -> list[dict]:
    today = datetime.today()
    start = today - timedelta(weeks=2)
    end = today + timedelta(weeks=8)

    r = await page.request.get(
        f"{BASE_URL}/WebUntis/api/homeworks/lessons",
        params={
            "startDate": int(start.strftime("%Y%m%d")),
            "endDate": int(end.strftime("%Y%m%d")),
        },
        headers=auth,
    )
    data = await r.json()
    hw_data = data.get("data", {})

    lessons_map = {l["id"]: l for l in hw_data.get("lessons", [])}

    homeworks = []
    for hw in hw_data.get("homeworks", []):
        text = (hw.get("text") or "").strip()
        if not text:
            continue

        lesson = lessons_map.get(hw.get("lessonId"), {})
        subject = lesson.get("subject", {}).get("name")

        due_raw = str(hw.get("dueDate", ""))
        due_date = f"{due_raw[:4]}-{due_raw[4:6]}-{due_raw[6:]}" if len(due_raw) == 8 else None

        prefix = f"{subject}: " if subject else ""
        max_body = 80 - len(prefix)
        title = prefix + (text[:max_body] + "…" if len(text) > max_body else text)

        homeworks.append({
            "webuntis_id": f"hw_{hw['id']}",
            "title": title,
            "description": text,
            "due_date": due_date,
            "priority": "medium",
        })

    return homeworks


async def _fetch_messages(page, auth: dict) -> list[dict]:
    try:
        r = await page.request.get(
            f"{BASE_URL}/WebUntis/api/rest/view/v1/messages",
            headers=auth,
        )
        data = await r.json()
        raw = data.get("data", {}).get("incomingMessages", [])

        messages = []
        for msg in raw:
            sender = msg.get("sender", {})
            sender_name = sender.get("displayName") or (
                f"{sender.get('firstName', '')} {sender.get('lastName', '')}".strip()
            )
            messages.append({
                "id": msg["id"],
                "subject": msg.get("subject", ""),
                "body": msg.get("content", msg.get("body", "")),
                "sender": sender_name,
                "sent_at": msg.get("sentDate", msg.get("createdDate", "")),
                "is_read": int(msg.get("isRead", False)),
            })
        return messages
    except Exception as e:
        print(f"Warning: could not fetch messages: {e}")
        return []
