import re
from datetime import date, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

MUDO_URL = "https://mudo.se/odenplan-barn-rott"
BOOKINGS_URL = "https://mudo.se/mina-bokningar"

# Persistent browser profile so the Mudo login (cookies) survives between runs.
PROFILE_DIR = Path.home() / ".local" / "share" / "taskboard" / "browser-profiles" / "mudo"

_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12,
}


_WEEKDAYS = {
    'måndag': 0, 'tisdag': 1, 'onsdag': 2, 'torsdag': 3,
    'fredag': 4, 'lördag': 5, 'söndag': 6,
}


def _parse_date_time(text: str) -> tuple[str, str]:
    """Parse Swedish date strings like 'Idag 16:30' or 'Måndag 30 jun 19:00'."""
    today = date.today()
    t = text.strip().lower()

    time_m = re.search(r'(\d{1,2}):(\d{2})', text)
    time_str = f"{int(time_m.group(1)):02d}:{time_m.group(2)}" if time_m else ''

    if 'idag' in t:
        return today.strftime('%Y-%m-%d'), time_str
    if 'imorgon' in t:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d'), time_str

    # "DD mon" pattern e.g. "30 jun"
    dm = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)', t)
    if dm:
        day, month = int(dm.group(1)), _MONTHS[dm.group(2)]
        year = today.year
        if (month, day) < (today.month, today.day):
            year += 1
        try:
            return date(year, month, day).strftime('%Y-%m-%d'), time_str
        except ValueError:
            pass

    # Weekday name e.g. "Måndag" — find the next occurrence of that weekday
    for name, wd in _WEEKDAYS.items():
        if name in t:
            days_ahead = (wd - today.weekday()) % 7
            return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d'), time_str

    return '', time_str


async def _wait_idle(page, timeout=15_000):
    try:
        await page.wait_for_load_state('networkidle', timeout=timeout)
    except Exception:
        pass


async def _dismiss_overlay(page):
    """Wait for any active Vuetify overlay to disappear before clicking."""
    try:
        await page.wait_for_selector('.v-overlay--active', state='hidden', timeout=8_000)
    except Exception:
        pass


async def sync_bookings() -> list[dict]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        await page.goto(MUDO_URL)
        await _wait_idle(page)

        # Log in if needed
        if await page.get_by_role('link', name='Logga in').count() > 0:
            await page.goto('https://mudo.se/login')
            await page.wait_for_function(
                "() => !window.location.pathname.includes('login')",
                timeout=300_000,
            )
            await page.goto(MUDO_URL)
            await _wait_idle(page)
            await page.wait_for_timeout(1000)

        print(f'[mudo] on page: {page.url}')

        bookings = []
        for _ in range(4):
            bookings.extend(await _scrape_week(page))
            next_btn = page.get_by_role('button', name='Nästa vecka')
            if await next_btn.count() == 0:
                break
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(400)
            await _dismiss_overlay(page)
            await next_btn.click()
            await _wait_idle(page)
            await page.wait_for_timeout(800)

        await ctx.close()
    return bookings


async def _scrape_week(page) -> list[dict]:
    bookings = []

    avboka_btns = page.locator('button, a').filter(has_text=re.compile(r'avboka', re.IGNORECASE))
    count = await avboka_btns.count()
    print(f'[mudo] avboka elements found: {count}')

    for i in range(count):
        btn = avboka_btns.nth(i)
        btn_text = (await btn.text_content() or '').strip().lower()
        status = 'waitlist' if 'kö' in btn_text else 'booked'

        # Climb up until we reach a node that contains a date (day name or "DD mon").
        card_text = await btn.evaluate("""
            el => {
                const dateRe = /(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag|\\d{1,2}\\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec))/i;
                let node = el;
                for (let i = 0; i < 12; i++) {
                    if (!node.parentElement) break;
                    node = node.parentElement;
                    if (dateRe.test(node.innerText || '')) break;
                }
                return (node.innerText || '').slice(0, 500);
            }
        """)
        print(f'[mudo] card: {card_text!r}')

        _SKIP = re.compile(
            r'^(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag'
            r'|\d{1,2}\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)'
            r'|\d{1,2}:\d{2}|\d+\s*min|info|du är bokad|avboka.*'
            r'|\d+\s*/\s*\d+\s*lediga)$',
            re.IGNORECASE,
        )
        lines = [l.strip() for l in card_text.splitlines()
                 if l.strip() and not _SKIP.match(l.strip())]
        title = lines[0] if lines else ''

        date_str, time_str = _parse_date_time(card_text)

        dur_m = re.search(r'(\d+)\s*min', card_text, re.IGNORECASE)
        duration_min = int(dur_m.group(1)) if dur_m else None

        room_m = re.search(r'MUDO\s*\S*', card_text, re.IGNORECASE)
        room = room_m.group(0).strip() if room_m else ''

        if date_str and title:
            bookings.append({
                'id': f"{date_str}_{time_str}_{title}",
                'date': date_str,
                'start_time': time_str,
                'duration_min': duration_min,
                'title': title,
                'instructors': '',
                'room': room,
                'status': status,
            })

    return bookings
