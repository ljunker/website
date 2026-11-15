import json
import re


def clean(value, newline=" "):
    """Make a value safe for tab-separated output.

    Line breaks are replaced by `newline`, tabs by a single space.
    """
    value = re.sub(r"\r\n|\n|\r", newline, value or "")
    return value.replace("\t", " ")


with open("events.json", "r", encoding="utf-8") as f:
    events = json.load(f)

for event in events:
    date = clean(event.get("date"))
    time = clean(event.get("time"))
    end_date = clean(event.get("end_date"))
    end_time = clean(event.get("end_time"))
    details = clean(event.get("details"))
    location = clean(event.get("location"), ", ")

    print(
        date + "\t"
        + time + "\t"
        + end_date + "\t"
        + end_time + "\t"
        + details + "\t"
        + location
    )
