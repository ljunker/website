from icalevents.icalevents import events
import datetime
import json
import pytz

four_weeks = datetime.timedelta(weeks=8)
dt = datetime.datetime.today()
in_four_weeks = dt + four_weeks
es = events("webcal://p131-caldav.icloud.com/published/2/MTAzODAyMzk0NDkxMDM4MKx0EePtPDXePVZMEANU5wgvh8UiCQKBUo_2X7Xqg9Jh3NtXpIyVy5CqwdHizblJlRvhMBUjjWdRQ3aI_qnXqcw", start=dt, end=in_four_weeks, sort=True, fix_apple=True)

events_json = []
utc_timezone = pytz.UTC

for e in es:
    start_utc = e.start.astimezone(utc_timezone)
    end_utc = e.end.astimezone(utc_timezone)
    event = {
            "date": start_utc.strftime("%Y-%m-%d"),
            "time": start_utc.strftime("%H:%M"),
            "end_date": end_utc.strftime("%Y-%m-%d"),
            "end_time": end_utc.strftime("%H:%M"),
            "details": e.summary,
            "location": e.location
    }
    events_json.append(event)

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events_json, f, ensure_ascii=False, indent=2)

print("Events gespeichert")