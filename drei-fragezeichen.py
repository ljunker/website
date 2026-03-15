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

def ensure_cached_image(url: str) -> str:
    if url == None:
        return ""
    parts = url.split("/")
    filename = parts[-2] + "_" + parts[-1]
    cache_path = Path("static/images/three") / filename
    if not cache_path.exists():
        print(f"Caching image from {url} to {cache_path}")
        response = requests.get(url)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(response.content)
    return str(cache_path).replace("static/", "/")

def main():
    response = requests.get(METADATA_URL)
    response.raise_for_status()
    metadata = response.json()

    collected = load_collected(COLLECTED_FILE)

    reduced = []
    for ep in metadata.get("serie", []):
        links = ep.get("links") or {}
        reduced.append({
            "nummer": ep.get("nummer"),
            "titel": ep.get("titel"),
            "collected": ep.get("nummer") in collected,
            "cover": ensure_cached_image(links.get("cover"))
        })

    OUTPUT_FILE.write_text(json.dumps(reduced, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output written to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
