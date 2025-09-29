import json
import requests
from pathlib import Path

METADATA_URL = "https://dreimetadaten.de/data/Serie.json"
COLLECTED_FILE = Path("drei-fragezeichen-collected.txt")
OUTPUT_FILE = Path("drei-fragezeichen.json")

def load_collected(path: Path) -> set[int]:
    text = path.read_text(encoding="utf-8").strip()
    numbers = set()
    for part in text.replace(",", " ").split():
        if part.strip().isdigit():
            numbers.add(int(part.strip()))
    return numbers

def main():
    response = requests.get(METADATA_URL)
    response.raise_for_status()
    metadata = response.json()

    collected = load_collected(COLLECTED_FILE)

    reduced = []
    for ep in metadata.get("serie", []):
        reduced.append({
            "nummer": ep.get("nummer"),
            "titel": ep.get("titel"),
            "collected": ep.get("nummer") in collected
        })

    OUTPUT_FILE.write_text(json.dumps(reduced, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()