"""Build static site for Brunnsskolan schedule."""

import asyncio
import shutil
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from skola24 import fetch_timetable
from ical import generate_ics
from skolmaten import fetch_menu

WEEKDAY_NAMES = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
MONTH_NAMES = [
    "", "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]

DIST = Path("docs")

SUBJECT_PALETTE = [
    "#818cf8",  # indigo
    "#34d399",  # emerald
    "#f472b6",  # pink
    "#fb923c",  # orange
    "#38bdf8",  # sky
    "#a78bfa",  # violet
    "#fbbf24",  # amber
    "#2dd4bf",  # teal
    "#f87171",  # red
    "#a3e635",  # lime
]

TEACHER_PALETTE = [
    "#93c5fd",  # blue
    "#86efac",  # green
    "#fda4af",  # rose
    "#fdba74",  # orange
    "#7dd3fc",  # sky
    "#c4b5fd",  # violet
    "#fcd34d",  # amber
    "#5eead4",  # teal
]


COLORS_FILE = Path("colors.toml")


def _load_colors():
    """Load saved color assignments from colors.toml."""
    if COLORS_FILE.exists():
        return tomllib.loads(COLORS_FILE.read_text())
    return {}


def _save_colors(data: dict):
    """Save color assignments to colors.toml."""
    lines = []
    for section, value in sorted(data.items()):
        if not isinstance(value, dict):
            continue
        # Check if this is a nested section (e.g. themes with sub-tables)
        has_subtables = any(isinstance(v, dict) for v in value.values())
        if has_subtables:
            # Simple key-value pairs first
            simple = {k: v for k, v in value.items() if not isinstance(v, dict)}
            if simple:
                lines.append(f"[{section}]")
                for k, v in sorted(simple.items()):
                    lines.append(f'"{k}" = "{v}"')
                lines.append("")
            # Then sub-tables
            for sub, mapping in sorted(value.items()):
                if isinstance(mapping, dict):
                    lines.append(f"[{section}.{sub}]")
                    for k, v in sorted(mapping.items()):
                        lines.append(f'"{k}" = "{v}"')
                    lines.append("")
        else:
            lines.append(f"[{section}]")
            for k, v in sorted(value.items()):
                lines.append(f'"{k}" = "{v}"')
            lines.append("")
    COLORS_FILE.write_text("\n".join(lines), encoding="utf-8")


def _color_map(values, palette, saved: dict):
    """Assign colors: keep saved ones, assign new from palette."""
    result = {}
    used = set(saved.values())
    next_idx = 0
    for v in sorted(values):
        if v in saved:
            result[v] = saved[v]
        else:
            # Find next unused palette color
            while palette[next_idx % len(palette)] in used and next_idx < len(palette) * 2:
                next_idx += 1
            color = palette[next_idx % len(palette)]
            result[v] = color
            used.add(color)
            next_idx += 1
    return result


def _group_lessons(lessons):
    """Group lessons that share the same time slot."""
    groups = []
    for lesson in lessons:
        if groups and groups[-1][0].start == lesson.start and groups[-1][0].end == lesson.end:
            groups[-1].append(lesson)
        else:
            groups.append([lesson])
    return groups


async def build():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    print(f"Hämtar schema för vecka {today.isocalendar().week}...")
    week_lessons = await fetch_timetable(monday, friday)

    print(f"Hämtar schema för kalender (30 dagar)...")
    calendar_lessons = await fetch_timetable(today, today + timedelta(days=30))

    print("Hämtar lunchmeny...")
    lunch_menu = fetch_menu()

    # Prepare template data
    saved = _load_colors()
    subject_colors = _color_map(
        {l.subject for l in week_lessons if l.subject},
        SUBJECT_PALETTE,
        saved.get("subjects", {}),
    )
    teacher_colors = _color_map(
        {l.teacher for l in week_lessons if l.teacher},
        TEACHER_PALETTE,
        saved.get("teachers", {}),
    )
    # Update only subjects/teachers in colors.toml, preserve everything else
    saved["subjects"] = subject_colors
    saved["teachers"] = teacher_colors
    _save_colors(saved)

    # Load theme from config.toml
    config = tomllib.loads(Path("config.toml").read_text())
    active_theme = config.get("theme", {}).get("active", "default")
    themes = saved.get("themes", {})
    theme = themes.get(active_theme, themes.get("default", {}))

    today_idx = today.weekday()  # 0=mon, 4=fri
    week_days = []
    for i in range(5):
        d = monday + timedelta(days=i)
        day_lessons = [l for l in week_lessons if l.date == d]
        week_days.append({
            "label": f"{WEEKDAY_NAMES[i][:3]} {d.day}/{d.month}",
            "weekday": WEEKDAY_NAMES[i],
            "date_str": f"{d.day} {MONTH_NAMES[d.month]} {d.year}",
            "is_today": d == today,
            "lessons": day_lessons,
            "groups": _group_lessons(day_lessons),
            "lunch_menu": lunch_menu.get(d, []),
        })

    weekday = WEEKDAY_NAMES[today.weekday()]
    date_str = f"{today.day} {MONTH_NAMES[today.month]} {today.year}"
    build_time = datetime.now(ZoneInfo("Europe/Stockholm")).strftime("%Y-%m-%d %H:%M")

    week_num = today.isocalendar().week
    week_range = f"{monday.day}/{monday.month} – {friday.day}/{friday.month}"

    # Render HTML
    env = Environment(loader=FileSystemLoader("templates"))

    shared = dict(
        theme=theme,
        subject_colors=subject_colors,
        teacher_colors=teacher_colors,
        week_days=week_days,
    )

    index_html = env.get_template("index.html").render(
        date_str=date_str,
        weekday=weekday,
        today_idx=today_idx,
        build_time=build_time,
        **shared,
    )

    week_html = env.get_template("vecka.html").render(
        week_num=week_num,
        week_range=week_range,
        **shared,
    )

    # Generate ICS
    ics_data = generate_ics(calendar_lessons)

    # Write output
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    (DIST / "index.html").write_text(index_html, encoding="utf-8")
    (DIST / "vecka.html").write_text(week_html, encoding="utf-8")
    (DIST / "calendar.ics").write_bytes(ics_data)

    print(f"Klart! {len(week_lessons)} lektioner i veckan.")
    print(f"Filer skrivna till {DIST}/")


if __name__ == "__main__":
    asyncio.run(build())
