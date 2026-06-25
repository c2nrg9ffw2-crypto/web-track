import re
from datetime import date, timedelta

from playwright.async_api import async_playwright

MUDO_URL = "https://mudo.se/odenplan-barn-rott"

_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12,
}


def _parse_date_time(text: str) -> tuple[str, str]:
    """Parse Swedish date strings like 'Idag 16:30' or 'Tisdag 30 jun 18:00'."""
    today = date.today()
    t = text.strip().lower()

    time_m = re.search(r'(\d{1,2}):(\d{2})', text)
    time_str = f"{int(time_m.group(1)):02d}:{time_m.group(2)}" if time_m else ''

    if t.startswith('idag'):
        return today.strftime('%Y-%m-%d'), time_str
    if t.startswith('imorgon'):
        return (today + timedelta(days=1)).strftime('%Y-%m-%d'), time_str

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

    return '', time_str


async def sync_bookings() -> list[dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto(MUDO_URL)
        await page.wait_for_load_state('networkidle')

        # Log in if needed
        if await page.get_by_role('link', name='Logga in').count() > 0:
            await page.goto('https://mudo.se/login')
            await page.wait_for_function(
                "() => !window.location.pathname.includes('login')",
                timeout=300_000,
            )
            await page.goto(MUDO_URL)
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(1000)

        bookings = []
        for _ in range(4):
            bookings.extend(await _scrape_week(page))
            next_btn = page.get_by_role('button', name='Nästa vecka')
            if await next_btn.count() == 0:
                break
            await next_btn.click()
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(800)

        await browser.close()
    return bookings


async def _scrape_week(page) -> list[dict]:
    bookings = []

    avboka_btns = page.get_by_role('button', name=re.compile(r'avboka', re.IGNORECASE))
    count = await avboka_btns.count()

    for i in range(count):
        btn = avboka_btns.nth(i)
        btn_text = (await btn.text_content() or '').strip().lower()
        status = 'waitlist' if 'kö' in btn_text else 'booked'

        await btn.click()
        await page.wait_for_timeout(600)

        dialog = page.locator('dialog')
        if not await dialog.count():
            continue

        title = ((await dialog.locator('h1').first.text_content()) or '').strip()

        # Date/time line contains HH:MM
        dt_els = dialog.locator('text=/\\d{1,2}:\\d{2}/')
        dt_text = ((await dt_els.first.text_content()) or '').strip() if await dt_els.count() else ''
        date_str, time_str = _parse_date_time(dt_text)

        # Duration
        dur_els = dialog.locator('text=/\\d+ min/')
        dur_text = ((await dur_els.first.text_content()) or '') if await dur_els.count() else ''
        dur_m = re.search(r'(\d+)\s*min', dur_text)
        duration_min = int(dur_m.group(1)) if dur_m else None

        # Room — line containing "MUDO"
        room_els = dialog.get_by_text(re.compile(r'MUDO', re.IGNORECASE))
        room = ((await room_els.first.text_content()) or '').strip() if await room_els.count() else ''

        # Instructors — anchor tags in dialog
        links = dialog.get_by_role('link')
        link_count = await links.count()
        instructors = [
            s for s in [
                ((await links.nth(j).text_content()) or '').strip()
                for j in range(link_count)
            ]
            if s and s != room
        ]

        # Close dialog
        await dialog.get_by_role('button').first.click()
        await page.wait_for_timeout(400)

        if date_str and title:
            bookings.append({
                'id': f"{date_str}_{time_str}_{title}",
                'date': date_str,
                'start_time': time_str,
                'duration_min': duration_min,
                'title': title,
                'instructors': ', '.join(instructors),
                'room': room,
                'status': status,
            })

    return bookings
