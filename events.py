from icalevents.icalevents import events
from zoneinfo import ZoneInfo
import datetime
import json

lookahead = datetime.timedelta(weeks=8)
dt = datetime.datetime.today() - datetime.timedelta(days=1)
until = dt + lookahead
es = events("webcal://p131-caldav.icloud.com/published/2/MTAzODAyMzk0NDkxMDM4MKx0EePtPDXePVZMEANU5wgvh8UiCQKBUo_2X7Xqg9Jh3NtXpIyVy5CqwdHizblJlRvhMBUjjWdRQ3aI_qnXqcw", start=dt, end=until, sort=True, fix_apple=True)

events_json = []
berlin = ZoneInfo("Europe/Berlin")


def to_berlin(value, all_day):
    # Ganztägige Termine kommen von icalevents als Mitternacht in einer
    # beliebigen Kalender-Zeitzone. Das Kalenderdatum soll erhalten bleiben,
    # daher nicht umrechnen.
    if all_day:
        return value
    return value.astimezone(berlin)


for e in es:
    start = to_berlin(e.start, e.all_day)
    end = to_berlin(e.end, e.all_day)
    event = {
            "date": start.strftime("%Y-%m-%d"),
            "time": start.strftime("%H:%M"),
            "end_date": end.strftime("%Y-%m-%d"),
            "end_time": end.strftime("%H:%M"),
            "details": e.summary,
            "location": e.location
    }
    events_json.append(event)

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events_json, f, ensure_ascii=False, indent=2)

print("Events gespeichert")
