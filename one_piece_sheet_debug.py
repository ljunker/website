#!/usr/bin/env python3
import csv
import io
import sys
import urllib.request

SHEET_ID = "1PZFS6bBs_187W75srTyNw0Bc5ZRJGBWUEuitlc1pdXs"
SHEET_NAME = "One Piece"
CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/gviz/tq?sheet={urllib.parse.quote(SHEET_NAME)}&tqx=out:csv"
)


def fetch_csv(url: str) -> str:
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    return data.decode("utf-8")


def parse_rows(text: str):
    reader = csv.reader(io.StringIO(text))
    return list(reader)


def main() -> int:
    # print(f"Fetching: {CSV_URL}")
    text = fetch_csv(CSV_URL)
    rows = parse_rows(text)

    # print(f"Total rows: {len(rows)}")
    if len(rows) < 4:
        print("Not enough rows; expected header at row 3, data from row 4.")
        return 1

    data_rows = rows[3:]
    # print(f"Data rows (after skipping 3): {len(data_rows)}")

    for row in data_rows:
        if not row:
            continue
        nummer = row[0].strip() if len(row) > 0 else ""
        status = row[1].strip() if len(row) > 1 else ""
        if not (nummer or status):
            continue
        print(f"{nummer}\t{status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
