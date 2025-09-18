import json
from datetime import datetime, timedelta
import pytz

with open("events.json", "r", encoding="utf-8") as f:
    events = json.load(f)

berlin = pytz.timezone("Europe/Berlin")

def add_berlin_offset(date_str: str, time_str: str) -> str:
    """
    Nimmt lokale deutsche Zeit (naiv), ermittelt per Datum CET/CEST-Offset
    und addiert diesen als Stunden auf die Zeit. 17:30 CEST -> 19:30.
    """
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        localized = berlin.localize(naive)
        offset = localized.utcoffset() or timedelta(0)
        adjusted = naive + offset
        return adjusted.strftime("%H:%M")
    except Exception:
        # Falls Parsing fehlschlägt, original Zeit zurückgeben
        return time_str or ""

for event in events:
    date = event.get("date") or ""
    time = event.get("time") or ""
    end_date = event.get("end_date") or ""
    end_time = event.get("end_time") or ""
    details = event.get("details") or ""
    location = (event.get("location") or "").replace("\n", ", ")

    time_out = add_berlin_offset(date, time)
    end_time_out = add_berlin_offset(end_date, end_time)

    print(
        date + "\t"
        + time_out + "\t"
        + end_date + "\t"
        + end_time_out + "\t"
        + details + "\t"
        + location
    )
