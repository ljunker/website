import json

with open("events.json", "r", encoding="utf-8") as f:
    events = json.load(f)

for event in events:
    date = event.get("date") or ""
    time = event.get("time") or ""
    end_date = event.get("end_date") or ""
    end_time = event.get("end_time") or ""
    details = event.get("details") or ""
    location = (event.get("location") or "").replace("\n", ", ")

    print(
        date + "\t"
        + time + "\t"
        + end_date + "\t"
        + end_time + "\t"
        + details + "\t"
        + location
    )
