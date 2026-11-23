"""Generate ICS calendar feed from lessons."""

from datetime import datetime, date
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from skola24 import Lesson

TZ = ZoneInfo("Europe/Stockholm")


def generate_ics(lessons: list[Lesson]) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Brunnsskolan 3RÖD//Schema//SV")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Brunnsskolan 3RÖD")
    cal.add("x-wr-timezone", "Europe/Stockholm")

    for lesson in lessons:
        if not lesson.subject:
            continue

        h_start, m_start = map(int, lesson.start.split(":"))
        h_end, m_end = map(int, lesson.end.split(":"))

        event = Event()
        event.add("summary", lesson.subject)
        event.add("dtstart", datetime(
            lesson.date.year, lesson.date.month, lesson.date.day,
            h_start, m_start, tzinfo=TZ,
        ))
        event.add("dtend", datetime(
            lesson.date.year, lesson.date.month, lesson.date.day,
            h_end, m_end, tzinfo=TZ,
        ))

        description_parts = []
        if lesson.teacher:
            description_parts.append(f"Lärare: {lesson.teacher}")
        if lesson.room:
            description_parts.append(f"Sal: {lesson.room}")
        if description_parts:
            event.add("description", "\n".join(description_parts))

        if lesson.room:
            event.add("location", lesson.room)

        uid = f"{lesson.date.isoformat()}-{lesson.start}-{lesson.subject}@brunnsskolan"
        event.add("uid", uid)

        cal.add_component(event)

    return cal.to_ical()
