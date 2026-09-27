"""
Builds data/rainfall_cache.json — REAL Open-Meteo 10-year rainfall statistics for
the demo region, bundled with the app so a deployment whose network blocks
Open-Meteo (the campus container) can still use measured rainfall there.

Run on a machine that CAN reach Open-Meteo:
    .venv/bin/python scripts/build_rainfall_cache.py

Points are fetched in priority order (exact demo sites, then a 0.1° grid over
Durg–Bhilai, then the curated villages). Open-Meteo's free tier weights a
10-year query as many calls, so the script stops cleanly on HTTP 429 and keeps
everything fetched so far; re-running later resumes and fills in the rest.
"""

import asyncio
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.rainfall import fetch_historical_rainfall, aggregate_rainfall, RainfallDataError, HISTORY_YEARS
from app.modules.village_search import PRESET_VILLAGES

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rainfall_cache.json")
PAUSE_S = 3.0

# 1. Exact demo points: contour sample pond site, sample land-area box, point demo.
DEMO_POINTS = [
    ("contours_1m.kml pond site", 21.24171, 81.28692),
    ("sample land-area box centre", 21.245, 81.288),
    ("point demo", 21.25, 81.29),
]
# 2. 0.1° grid over Durg–Bhilai (the demo watershed and surroundings).
GRID = [(f"grid {la:.1f},{lo:.1f}", round(la, 1), round(lo, 1))
        for la in (21.0, 21.1, 21.2, 21.3, 21.4) for lo in (81.1, 81.2, 81.3, 81.4, 81.5)]
# 3. Curated villages (Chhattisgarh first, then the rest).
VILLAGES = sorted(
    [(f"village {v['name']}", v["lat"], v["lon"]) for v in PRESET_VILLAGES],
    key=lambda p: 0 if 17.5 < p[1] < 23 and 80 < p[2] < 83 else 1,
)


def _load():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {"source": "Open-Meteo Historical Weather API (archive-api.open-meteo.com)", "points": []}


async def main():
    cache = _load()
    have = {(round(p["lat"], 4), round(p["lon"], 4)) for p in cache["points"]}
    today = date.today()
    cache["period"] = f"{today.year - HISTORY_YEARS}-{today.year - 1}"

    for label, lat, lon in DEMO_POINTS + GRID + VILLAGES:
        if (round(lat, 4), round(lon, 4)) in have:
            continue
        try:
            raw = await fetch_historical_rainfall(lat, lon)
            r = aggregate_rainfall(raw)
        except RainfallDataError as e:
            if "429" in str(e):
                print(f"Rate limited after {len(cache['points'])} points — re-run later to continue.")
                break
            print(f"skip {label}: {e}")
            continue
        cache["points"].append({
            "label": label, "lat": lat, "lon": lon,
            "annual_avg_mm": r.annual_avg_mm,
            "monsoon_mm": r.seasonal["monsoon_mm"],
            "non_monsoon_mm": r.seasonal["non_monsoon_mm"],
            "data_years": r.data_years,
        })
        have.add((round(lat, 4), round(lon, 4)))
        print(f"{label}: {r.annual_avg_mm} mm/yr, monsoon {r.seasonal['monsoon_mm']} mm")
        cache["generated"] = today.isoformat()
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1)
        await asyncio.sleep(PAUSE_S)

    print(f"{len(cache['points'])} points in {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
