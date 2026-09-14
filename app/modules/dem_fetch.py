"""
DEM fetch — downloads an elevation raster (GeoTIFF) from OpenTopography for a
bounding box around a point.

IMPORTANT: this function is written for real, but has NOT been network-tested here —
this sandbox can't reach opentopography.org (network policy). Your campus network may
also block it (per your earlier note about external repos/DNS being blocked at IIT Bhilai).
Test this from off-campus, a hotspot, or a VPN that isn't blocked before demo day.

Get a free API key at: https://opentopography.org/  (Account -> myOpenTopo -> Request API key)
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()  # ensures .env is read even if this module is imported before app/db/database.py

OPENTOPOGRAPHY_API_KEY = os.environ.get("OPENTOPOGRAPHY_API_KEY", "")
OPENTOPOGRAPHY_URL = "https://portal.opentopography.org/API/globaldem"


async def fetch_dem_tile(lat: float, lon: float, buffer_deg: float = 0.05, out_path: str = "/tmp/dem_tile.tif") -> str:
    """
    Downloads an SRTM 30m DEM tile covering a small bounding box around (lat, lon).

    in  -> lat, lon: center point; buffer_deg: how far to extend the box in each direction
    out -> path to the downloaded GeoTIFF file

    Raises: TerrainDataError if the download fails (bad key, API down, network blocked, etc.)
    """
    from app.modules.terrain import TerrainDataError  # local import avoids circular import

    if not OPENTOPOGRAPHY_API_KEY:
        raise TerrainDataError("OPENTOPOGRAPHY_API_KEY not set — see .env.example")

    params = {
        "demtype": "SRTMGL1",  # 30m resolution
        "south": lat - buffer_deg,
        "north": lat + buffer_deg,
        "west": lon - buffer_deg,
        "east": lon + buffer_deg,
        "outputFormat": "GTiff",
        "API_Key": OPENTOPOGRAPHY_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(OPENTOPOGRAPHY_URL, params=params)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
        return out_path
    except httpx.HTTPError as e:
        raise TerrainDataError(f"DEM download failed: {e}")
