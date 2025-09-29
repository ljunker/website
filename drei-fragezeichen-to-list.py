import json

with open("drei-fragezeichen.json", "r", encoding="utf-8") as f:
    episodes = json.load(f)

for episode in episodes:
    nummer = episode.get("nummer") or ""
    titel = episode.get("titel") or ""
    collected = episode.get("collected") or ""

    print(
        str(nummer) + "\t"
        + titel + "\t"
        + ("gesammelt" if collected else "nicht gesammelt")
    )
