#!/usr/bin/env python3
"""Lokaler Dev-Server: liefert ./_site aus und simuliert /schedule/calendar.ics.

Produktiv leitet nginx den Feed an iCloud weiter; lokal gibt es ihn nicht.
Dieser Server erzeugt zur Laufzeit einen Beispiel-Feed mit Terminen relativ
zu heute (nur fiktive Daten). Es wird nichts in _site geschrieben.

Umgebungsvariablen:
  PORT      Port (Standard 8000)
  CALENDAR  leer = Beispiel-Feed, "empty" = leerer Feed, "error" = HTTP 500
"""
import datetime as dt
import functools
import http.server
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_site")
FEED_PATH = "/schedule/calendar.ics"

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
DTSTART:19810329T020000
TZNAME:MESZ
TZOFFSETTO:+0200
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
DTSTART:19961027T030000
TZNAME:MEZ
TZOFFSETTO:+0100
END:STANDARD
END:VTIMEZONE"""


def local(day, hm):
    return day.strftime("%Y%m%d") + "T" + hm + "00"


def utc(day, hh, mm):
    return dt.datetime(day.year, day.month, day.day, hh, mm).strftime("%Y%m%dT%H%M00Z")


def event(uid, lines):
    return ["BEGIN:VEVENT", "UID:%s@example.invalid" % uid,
            "DTSTAMP:20260101T000000Z"] + lines + ["END:VEVENT"]


def fold(line, limit=75):
    """Faltet eine Zeile nach RFC 5545 (max. 75 Oktette, UTF-8-sicher)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


def sample_feed():
    today = dt.date.today()

    def d(n):
        return today + dt.timedelta(days=n)

    tz = "TZID=Europe/Berlin"
    ev = []
    # woechentlich wiederkehrend (RRULE) mit URL, ab letzter Woche
    start = d(-7)
    ev += event("weekly", [
        "SUMMARY:Wochentanz im Eichenhof",
        "LOCATION:Eichenweg 12\\, 12345 Musterstadt",
        "URL:https://example.invalid/eichenhof",
        "DTSTART;%s:%s" % (tz, local(start, "1930")),
        "DTEND;%s:%s" % (tz, local(start, "2130")),
        "RRULE:FREQ=WEEKLY",
    ])
    # verschobene Einzelinstanz dieser Serie (uebernimmt die URL der Serie)
    orig = d(14)
    orig = orig - dt.timedelta(days=(orig - start).days % 7)
    moved = orig + dt.timedelta(days=2)
    ev += event("weekly", [
        "SUMMARY:Wochentanz im Eichenhof (verschoben)",
        "LOCATION:Eichenweg 12\\, 12345 Musterstadt",
        "RECURRENCE-ID;%s:%s" % (tz, local(orig, "1930")),
        "DTSTART;%s:%s" % (tz, local(moved, "1800")),
        "DTEND;%s:%s" % (tz, local(moved, "2000")),
    ])
    # Einzeltermin mit URL
    ev += event("single-url", [
        "SUMMARY:Tanzclub Lindenblatt",
        "LOCATION:Gemeindehaus Lindenallee 3\\, 54321 Beispieldorf",
        "URL:https://example.invalid/lindenblatt",
        "DTSTART;%s:%s" % (tz, local(d(3), "2000")),
        "DTEND;%s:%s" % (tz, local(d(3), "2200")),
    ])
    # Einzeltermin ohne URL, Ende = Anfang
    ev += event("single", [
        "SUMMARY:Schnuppertanz Sonnenhof",
        "LOCATION:Sonnenhof\\, Wiesenstrasse 7\\, 11111 Testheim",
        "DTSTART:%s" % utc(d(5), 17, 0),
        "DTEND:%s" % utc(d(5), 17, 0),
    ])
    # ohne Ort
    ev += event("no-location", [
        "SUMMARY:Online-Callertreffen",
        "DTSTART;%s:%s" % (tz, local(d(9), "1900")),
        "DTEND;%s:%s" % (tz, local(d(9), "2030")),
    ])
    # sehr langer Club- und Ortsname
    ev += event("long", [
        "SUMMARY:Verein zur Foerderung des traditionellen Gesellschaftstanzes "
        "und verwandter Volkstanzkulturen Nord-Sued e.V. Ortsgruppe Hinterwaeldlingen",
        "LOCATION:Mehrzweckhalle der Grundschule am Kleinen Bach\\, Hauptstrasse "
        "123 a\\, Ortsteil Oberunterdorf-Mittelhausen\\, 99999 Langenamenstadt",
        "DTSTART;%s:%s" % (tz, local(d(12), "1815")),
        "DTEND;%s:%s" % (tz, local(d(12), "2045")),
    ])
    # ganztaegig
    ev += event("allday", [
        "SUMMARY:Tanzwochenende Seeblick",
        "LOCATION:Jugendherberge Seeblick\\, 22222 Seestadt",
        "DTSTART;VALUE=DATE:%s" % d(20).strftime("%Y%m%d"),
        "DTEND;VALUE=DATE:%s" % d(21).strftime("%Y%m%d"),
    ])
    # weit in der Zukunft (> 8 Wochen)
    ev += event("later1", [
        "SUMMARY:Sommerfest Tanzgruppe Waldrand",
        "LOCATION:Festwiese Waldrand\\, 33333 Grünau",
        "URL:https://example.invalid/waldrand",
        "DTSTART;%s:%s" % (tz, local(d(75), "1600")),
        "DTEND;%s:%s" % (tz, local(d(75), "1900")),
    ])
    ev += event("later2", [
        "SUMMARY:Neujahrstanz Rosengarten",
        "LOCATION:Rosengarten-Saal\\, Rosenstrasse 1\\, 44444 Blumenau",
        "DTSTART;%s:%s" % (tz, local(d(130), "2000")),
        "DTEND;%s:%s" % (tz, local(d(130), "2300")),
    ])
    lines = (["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//dev-server//DE",
              "CALSCALE:GREGORIAN"] + VTIMEZONE.split("\n") + ev
             + ["END:VCALENDAR"])
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def empty_feed():
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//dev-server//DE\r\nEND:VCALENDAR\r\n"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == FEED_PATH:
            mode = os.environ.get("CALENDAR", "").lower()
            if mode == "error":
                self.send_error(500, "Simulierter Fehler (CALENDAR=error)")
                return
            body = (empty_feed() if mode == "empty" else sample_feed()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8000"))
    root = os.path.abspath(ROOT)
    if not os.path.isdir(root):
        sys.exit("%s fehlt, zuerst 'make build' ausführen" % root)
    handler = functools.partial(Handler, directory=root)
    with http.server.ThreadingHTTPServer(("", port), handler) as srv:
        print("Serving %s on http://localhost:%d (CALENDAR=%s)"
              % (root, port, os.environ.get("CALENDAR", "") or "sample"))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
