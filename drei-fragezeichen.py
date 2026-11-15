import json
import sys
import requests
from io import BytesIO
from pathlib import Path
from PIL import Image

METADATA_URL = "https://dreimetadaten.de/data/Serie.json"
COLLECTED_FILE = Path("drei-fragezeichen-collected.txt")
OUTPUT_FILE = Path("drei-fragezeichen.json")
MAX_COVER_SIZE = 200  # angezeigt werden 100x100 px, 200 px = 2x fuer Retina

def load_collected(path: Path) -> set[int]:
    text = path.read_text(encoding="utf-8").strip()
    numbers = set()
    for part in text.replace(",", " ").split():
        if part.strip().isdigit():
            numbers.add(int(part.strip()))
    return numbers

def ensure_cached_image(url: str) -> str:
    if url is None:
        return ""
    parts = url.split("/")
    filename = parts[-2] + "_" + Path(parts[-1]).stem + ".webp"
    cache_path = Path("static/images/three") / filename
    if not cache_path.exists():
        print(f"Caching image from {url} to {cache_path}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(BytesIO(response.content)) as img:
            img = img.convert("RGB")
            img.thumbnail((MAX_COVER_SIZE, MAX_COVER_SIZE), Image.LANCZOS)
            img.save(cache_path, "WEBP", quality=80)
    return str(cache_path).replace("static/", "/")

def update_existing_output(collected: set[int]) -> None:
    """Fallback ohne Netz: vorhandene JSON behalten, nur collected-Flags aktualisieren."""
    episodes = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    for ep in episodes:
        ep["collected"] = ep.get("nummer") in collected
    OUTPUT_FILE.write_text(json.dumps(episodes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Output written to {OUTPUT_FILE} (from existing data)")

def main():
    collected = load_collected(COLLECTED_FILE)

    try:
        response = requests.get(METADATA_URL, timeout=30)
        response.raise_for_status()
        metadata = response.json()
    except (requests.RequestException, ValueError) as e:
        if not OUTPUT_FILE.exists():
            raise
        print(f"WARNUNG: {METADATA_URL} nicht abrufbar ({e}), "
              f"verwende vorhandene {OUTPUT_FILE}", file=sys.stderr)
        update_existing_output(collected)
        return

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
