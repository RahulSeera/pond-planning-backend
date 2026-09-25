"""
Village search module — provides search functionality for Indian villages and rural locations.
Matches requirements from §5 of the High-Level Design (HLD).

Combines:
  1. A curated in-memory dataset of rural regions, districts, and villages across India
     (with a focus on Chhattisgarh / central India where test sites are located).
  2. Dynamic fallback to OpenStreetMap Nominatim geocoding for any village or town name.
"""

import httpx
from typing import List, Dict, Any

# Curated reference villages with accurate coordinates
PRESET_VILLAGES: List[Dict[str, Any]] = [
    {"id": 1, "name": "Bhilai Rural (Kutelabhata)", "district": "Durg", "state": "Chhattisgarh", "lat": 21.2180, "lon": 81.3390},
    {"id": 2, "name": "Patan Village", "district": "Durg", "state": "Chhattisgarh", "lat": 21.0371, "lon": 81.5369},
    {"id": 3, "name": "Abhanpur", "district": "Raipur", "state": "Chhattisgarh", "lat": 21.0543, "lon": 81.7483},
    {"id": 4, "name": "Arang Village", "district": "Raipur", "state": "Chhattisgarh", "lat": 21.1963, "lon": 81.9688},
    {"id": 5, "name": "Dhamtari Rural", "district": "Dhamtari", "state": "Chhattisgarh", "lat": 20.7071, "lon": 81.5498},
    {"id": 6, "name": "Kurud", "district": "Dhamtari", "state": "Chhattisgarh", "lat": 20.8268, "lon": 81.7163},
    {"id": 7, "name": "Gunderdehi", "district": "Balod", "state": "Chhattisgarh", "lat": 20.9427, "lon": 81.2941},
    {"id": 8, "name": "Simga", "district": "Baloda Bazar", "state": "Chhattisgarh", "lat": 21.6288, "lon": 81.6997},
    {"id": 9, "name": "Bemetara Rural", "district": "Bemetara", "state": "Chhattisgarh", "lat": 21.7032, "lon": 81.5458},
    {"id": 10, "name": "Khairagarh", "district": "Rajnandgaon", "state": "Chhattisgarh", "lat": 21.4190, "lon": 80.9786},
    {"id": 11, "name": "Dongargarh Rural", "district": "Rajnandgaon", "state": "Chhattisgarh", "lat": 21.1895, "lon": 80.7607},
    {"id": 12, "name": "Bilaspur Rural (Kota)", "district": "Bilaspur", "state": "Chhattisgarh", "lat": 22.2965, "lon": 82.0253},
    {"id": 13, "name": "Takhatpur", "district": "Bilaspur", "state": "Chhattisgarh", "lat": 22.1481, "lon": 81.8679},
    {"id": 14, "name": "Champa Rural", "district": "Janjgir-Champa", "state": "Chhattisgarh", "lat": 22.0439, "lon": 82.6575},
    {"id": 15, "name": "Kanker Basin", "district": "Kanker", "state": "Chhattisgarh", "lat": 20.2719, "lon": 81.4925},
    {"id": 16, "name": "Jagdalpur Rural", "district": "Bastar", "state": "Chhattisgarh", "lat": 19.0734, "lon": 82.0298},
    {"id": 17, "name": "Kondagaon", "district": "Kondagaon", "state": "Chhattisgarh", "lat": 19.5973, "lon": 81.6669},
    {"id": 18, "name": "Ralegan Siddhi", "district": "Ahmednagar", "state": "Maharashtra", "lat": 19.0069, "lon": 74.4533},
    {"id": 19, "name": "Hiware Bazar", "district": "Ahmednagar", "state": "Maharashtra", "lat": 19.1678, "lon": 74.8872},
    {"id": 20, "name": "Baramati Rural", "district": "Pune", "state": "Maharashtra", "lat": 18.1520, "lon": 74.5770},
    {"id": 21, "name": "Laporiya (Water Harvest Model)", "district": "Dudu/Jaipur", "state": "Rajasthan", "lat": 26.6025, "lon": 75.1489},
    {"id": 22, "name": "Piplantri", "district": "Rajsamand", "state": "Rajasthan", "lat": 25.0450, "lon": 73.8767},
    {"id": 23, "name": "Bari", "district": "Dholpur", "state": "Rajasthan", "lat": 26.6508, "lon": 77.6163},
    {"id": 24, "name": "Panna Rural", "district": "Panna", "state": "Madhya Pradesh", "lat": 24.7196, "lon": 80.1979},
    {"id": 25, "name": "Mandla Basin", "district": "Mandla", "state": "Madhya Pradesh", "lat": 22.5986, "lon": 80.3712},
]


async def search_villages(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Searches for villages matching the query.
    First checks preset known rural areas, then falls back to Nominatim OSM search if needed.
    """
    q = query.strip().lower()
    if not q:
        return PRESET_VILLAGES[:limit]

    # 1. Match against preset villages
    matches = []
    for v in PRESET_VILLAGES:
        searchable = f"{v['name']} {v['district']} {v['state']}".lower()
        if q in searchable:
            matches.append(v)
            if len(matches) >= limit:
                return matches

    # 2. If fewer than limit matches and network is available, query Nominatim
    if len(matches) < limit:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            headers = {"User-Agent": "PondPlanningSystem/1.0 (academic; student@college.edu)"}
            params = {
                "q": f"{query}, India",
                "format": "json",
                "addressdetails": 1,
                "limit": limit - len(matches),
            }
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    start_id = 1000 + len(matches)
                    for item in data:
                        addr = item.get("address", {})
                        district = addr.get("county") or addr.get("state_district") or addr.get("city") or ""
                        state = addr.get("state", "India")
                        matches.append({
                            "id": start_id,
                            "name": item.get("name") or item.get("display_name", "").split(",")[0],
                            "district": district,
                            "state": state,
                            "lat": float(item["lat"]),
                            "lon": float(item["lon"]),
                        })
                        start_id += 1
        except Exception:
            pass  # Non-blocking graceful degradation

    return matches[:limit]
