#!/usr/bin/env python3
"""Liest das One-Piece-Google-Sheet und gibt die Bände aus.

Ohne Argument: "nummer<TAB>status" pro Zeile (für make/make-one-piece-index).
Mit "--js VARNAME": "const VARNAME = {...};" (für static/one-piece.html).
"""
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request

SHEET_ID = "1PZFS6bBs_187W75srTyNw0Bc5ZRJGBWUEuitlc1pdXs"
SHEET_NAME = "One Piece"
CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?sheet={urllib.parse.quote(SHEET_NAME)}&tqx=out:csv"
)
VARNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()
    return data.decode("utf-8")


def parse_rows(text: str):
    reader = csv.reader(io.StringIO(text))
    return list(reader)


def data_rows(rows):
    """Einzige Stelle, die die Datenzeilen bestimmt.

    Die ersten 3 Zeilen sind Kopf (Link, Zahlen, "Status"); ab Zeile 4 stehen
    die Daten. Zeilen ohne Nummer und Status werden übersprungen.
    Liefert eine Liste von (nummer, status).
    """
    result = []
    for row in rows[3:]:
        nummer = row[0].strip() if len(row) > 0 else ""
        status = row[1].strip() if len(row) > 1 else ""
        if not (nummer or status):
            continue
        result.append((nummer, status))
    return result


def clean_cell(value: str) -> str:
    return " ".join(value.split())


def main(argv) -> int:
    js_var = None
    if len(argv) == 0:
        pass
    elif len(argv) == 2 and argv[0] == "--js":
        js_var = argv[1]
        if not VARNAME_RE.fullmatch(js_var):
            print(f"Ungültiger Variablenname: {js_var!r}", file=sys.stderr)
            return 2
    else:
        print("Aufruf: one_piece_sheet.py [--js VARNAME]", file=sys.stderr)
        return 2

    rows = parse_rows(fetch_csv(CSV_URL))
    if len(rows) < 4:
        print(
            "Not enough rows; expected header at row 3, data from row 4.",
            file=sys.stderr,
        )
        return 1

    items = data_rows(rows)

    if js_var is None:
        for nummer, status in items:
            print(f"{clean_cell(nummer)}\t{clean_cell(status)}")
        return 0

    payload = {
        "name": "Lars Junker One Piece Sammlung",
        "site": "https://kryptikk.de",
        "generated": int(time.time()),
        "baende": [{"nummer": n, "status": s} for n, s in items],
    }
    print(f"const {js_var} = {json.dumps(payload, ensure_ascii=False)};")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
