"""Skola24 API client for fetching timetable data."""

import asyncio
import tomllib
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import httpx

_cfg = tomllib.loads(Path(__file__).with_name("config.toml").read_text())["skola24"]

API_BASE = _cfg["api_base"]
HEADERS = {
    "X-Scope": _cfg["x_scope"],
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
HOST = _cfg["host"]
UNIT_GUID = _cfg["unit_guid"]
CLASS_NAME = _cfg["class_name"]


@dataclass
class Lesson:
    date: date
    start: str  # HH:MM
    end: str    # HH:MM
    subject: str
    teacher: str
    room: str
    color: str


async def _post(client: httpx.AsyncClient, path: str, body: dict | None = None) -> dict:
    resp = await client.post(f"{API_BASE}{path}", json=body, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


async def _get_school_year(client: httpx.AsyncClient) -> str:
    data = await _post(client, "/get/active/school/years", {
        "hostName": HOST,
        "checkSchoolYearsFeatures": False,
    })
    today = date.today()
    for sy in data["data"]["activeSchoolYears"]:
        start = datetime.fromisoformat(sy["from"]).date()
        end = datetime.fromisoformat(sy["to"]).date()
        if start <= today <= end:
            return sy["guid"]
    return data["data"]["activeSchoolYears"][0]["guid"]


async def _get_class_guid(client: httpx.AsyncClient) -> str:
    data = await _post(client, "/get/timetable/selection", {
        "hostName": HOST,
        "unitGuid": UNIT_GUID,
        "filters": {
            "class": True, "course": False, "group": False,
            "period": False, "room": False, "student": False,
            "subject": False, "teacher": False,
        },
    })
    for cls in data["data"]["classes"]:
        if cls["groupName"] == CLASS_NAME:
            return cls["groupGuid"]
    raise ValueError(f"Class {CLASS_NAME} not found")


async def _get_render_key(client: httpx.AsyncClient) -> str:
    data = await _post(client, "/get/timetable/render/key", None)
    return data["data"]["key"]


def _monday_of_week(year: int, week: int) -> date:
    return date.fromisocalendar(year, week, 1)


async def _fetch_week(
    client: httpx.AsyncClient,
    school_year: str,
    class_guid: str,
    year: int,
    week: int,
) -> list[Lesson]:
    render_key = await _get_render_key(client)
    await asyncio.sleep(0.3)

    data = await _post(client, "/render/timetable", {
        "renderKey": render_key,
        "host": HOST,
        "unitGuid": UNIT_GUID,
        "schoolYear": school_year,
        "width": 1280,
        "height": 720,
        "selectionType": 0,
        "selection": class_guid,
        "scheduleDay": 0,
        "week": week,
        "year": year,
        "startDate": None,
        "endDate": None,
        "blackAndWhite": False,
        "showHeader": False,
        "periodText": "",
        "privateFreeTextMode": False,
        "privateSelectionMode": None,
        "customerKey": "",
        "personalTimetable": False,
    })

    timetable = data.get("data", {})
    lesson_infos = timetable.get("lessonInfo") or []
    box_list = timetable.get("boxList") or []

    # Build color map from boxList
    color_map: dict[str, str] = {}
    for box in box_list:
        color = box.get("bColor", "#6366f1")
        for guid in (box.get("lessonGuids") or []):
            color_map[guid] = color

    monday = _monday_of_week(year, week)
    lessons = []
    for info in lesson_infos:
        texts = info.get("texts", [])
        day_num = info.get("dayOfWeekNumber", 1)
        lesson_date = monday + timedelta(days=day_num - 1)
        t_start = info.get("timeStart", "00:00:00")[:5]
        t_end = info.get("timeEnd", "00:00:00")[:5]
        guid = info.get("guidId", "")

        lessons.append(Lesson(
            date=lesson_date,
            start=t_start,
            end=t_end,
            subject=texts[0] if len(texts) > 0 else "",
            teacher=texts[1] if len(texts) > 1 else "",
            room=texts[2] if len(texts) > 2 else "",
            color=color_map.get(guid, "#6366f1"),
        ))

    return lessons


async def fetch_timetable(start_date: date, end_date: date) -> list[Lesson]:
    """Fetch timetable lessons for a date range."""
    async with httpx.AsyncClient() as client:
        school_year = await _get_school_year(client)
        await asyncio.sleep(0.3)
        class_guid = await _get_class_guid(client)
        await asyncio.sleep(0.3)

        # Collect unique weeks needed
        weeks: set[tuple[int, int]] = set()
        d = start_date
        while d <= end_date:
            iso = d.isocalendar()
            weeks.add((iso.year, iso.week))
            d += timedelta(days=7)
        # Also add the end_date's week
        iso = end_date.isocalendar()
        weeks.add((iso.year, iso.week))

        all_lessons: list[Lesson] = []
        for year, week in sorted(weeks):
            lessons = await _fetch_week(client, school_year, class_guid, year, week)
            all_lessons.extend(lessons)
            await asyncio.sleep(0.3)

    # Filter to requested range
    return sorted(
        [l for l in all_lessons if start_date <= l.date <= end_date],
        key=lambda l: (l.date, l.start),
    )
