"""Fetch school lunch menu from skolmaten.se RSS feed."""

import tomllib
from datetime import date
from xml.etree import ElementTree

import httpx

_config = tomllib.loads(open("config.toml", "rb").read().decode())
_sm = _config.get("skolmaten", {})
ENABLED = _sm.get("enabled", False)
SCHOOL = _sm.get("school", "")

RSS_URL = f"https://skolmaten.se/api/4/rss/week/{SCHOOL}?locale=sv"

WEEKDAY_MAP = {
    "Måndag": 0, "Tisdag": 1, "Onsdag": 2,
    "Torsdag": 3, "Fredag": 4,
}


def fetch_menu() -> dict[date, list[str]]:
    """Fetch weekly lunch menu. Returns {date: [dish1, dish2, ...]}."""
    if not ENABLED or not SCHOOL:
        return {}

    resp = httpx.get(RSS_URL, timeout=10)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)
    result = {}

    for item in root.iter("item"):
        pub = item.findtext("pubDate", "")
        desc = item.findtext("description", "")

        # Parse date from pubDate: "Mon, 02 Mar 2026 00:00:00 GMT"
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub).date()
        except Exception:
            continue

        # Parse dishes from description: "Dish1 (tag), <br/>Dish2 (tag)"
        dishes = [d.strip() for d in desc.split("<br/>") if d.strip()]
        if dishes:
            result[dt] = dishes

    return result
