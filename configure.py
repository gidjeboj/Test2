"""Interactive setup – creates config.toml by querying the Skola24 API."""

from pathlib import Path

import httpx

API_BASE = "https://web.skola24.se/api"
X_SCOPE = "8a22163c-8662-4535-9050-bc5e1923df48"
HEADERS = {
    "X-Scope": X_SCOPE,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}


def _post(client: httpx.Client, path: str, body: dict | None = None) -> dict:
    resp = client.post(f"{API_BASE}{path}", json=body, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _pick(items: list, prompt: str) -> int:
    """Let user pick from a numbered list. Returns chosen index."""
    while True:
        try:
            choice = int(input(f"\n{prompt} [1-{len(items)}]: "))
            if 1 <= choice <= len(items):
                return choice - 1
        except (ValueError, EOFError):
            pass
        print(f"  Ange ett nummer mellan 1 och {len(items)}")


def main():
    print("=== Skola24 Schema – Konfiguration ===\n")

    kommun = input("Kommun (t.ex. orebro): ").strip().lower()
    host = f"{kommun}.skola24.se"
    print(f"→ {host}")

    with httpx.Client() as client:
        # Hämta skolor
        print("\nHämtar skolor...")
        data = _post(client, "/services/skola24/get/timetable/viewer/units", {
            "getTimetableViewerUnitsRequest": {"hostName": host},
        })
        units = (
            data.get("data", {})
            .get("getTimetableViewerUnitsResponse", {})
            .get("units", [])
        )
        if not units:
            print(f"Inga skolor hittades för {host}")
            return

        units.sort(key=lambda u: u.get("unitId", ""))
        for i, u in enumerate(units, 1):
            print(f"  {i}. {u.get('unitId', '?')}")

        idx = _pick(units, "Välj skola")
        school = units[idx]
        unit_guid = school["unitGuid"]
        school_name = school.get("unitId", "?")
        print(f"→ {school_name}")

        # Hämta klasser
        print("\nHämtar klasser...")
        data = _post(client, "/get/timetable/selection", {
            "hostName": host,
            "unitGuid": unit_guid,
            "filters": {
                "class": True, "course": False, "group": False,
                "period": False, "room": False, "student": False,
                "subject": False, "teacher": False,
            },
        })
        classes = data.get("data", {}).get("classes", [])
        if not classes:
            print("Inga klasser hittades")
            return

        classes.sort(key=lambda c: c.get("groupName", ""))
        for i, c in enumerate(classes, 1):
            print(f"  {i}. {c['groupName']}")

        idx = _pick(classes, "Välj klass")
        chosen_class = classes[idx]
        class_name = chosen_class["groupName"]
        print(f"→ {class_name}")

    # Skriv config.toml
    config_path = Path(__file__).with_name("config.toml")
    config_path.write_text(
        f'[skola24]\n'
        f'api_base = "{API_BASE}"\n'
        f'x_scope = "{X_SCOPE}"\n'
        f'host = "{host}"\n'
        f'unit_guid = "{unit_guid}"\n'
        f'class_name = "{class_name}"\n',
        encoding="utf-8",
    )

    print(f"\nKlart! Konfiguration sparad i {config_path.name}")
    print(f"Kör nu: uv run python build.py")


if __name__ == "__main__":
    main()
