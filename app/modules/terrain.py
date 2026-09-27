"""
Terrain Module — DEM fetch + catchment delineation (D8 flow direction).

This is now REAL (not a stub): it calls dem_fetch.py to get a DEM tile, then
catchment.py to run the actual D8/flow-accumulation algorithm and produce a
real catchment polygon + area + slope.

CAVEAT: dem_fetch.py's network call to OpenTopography hasn't been tested from
this sandbox (network policy blocks it) — test it from your own machine before
relying on it for the demo. catchment.py's algorithm IS tested (see tests/test_terrain.py),
using a synthetic DEM standing in for a real downloaded one.
"""

import asyncio
import os
import tempfile

from app.schemas import TerrainResult
from app.modules.dem_fetch import fetch_dem_tile
from app.modules.catchment import delineate_catchment, catchment_to_geojson


# DEM half-widths (degrees) tried in order: if the catchment still reaches the
# tile edge, one larger tile is fetched before giving up and warning.
DEM_BUFFERS_DEG = (0.05, 0.12)
TRUNCATED_WARNING = (
    "The catchment reaches the edge of the downloaded elevation tile, so the true upstream "
    "area may be larger than reported — treat catchment area and runoff as lower bounds."
)


async def get_catchment(lat: float, lon: float) -> tuple[TerrainResult, list[str]]:
    """
    Interface contract:
      in  -> lat, lon of the selected point
      out -> (TerrainResult with catchment polygon, area, and average slope,
              list of warnings for the caller to surface)

    Raises: TerrainDataError if the DEM can't be fetched/processed.
    """
    warnings: list[str] = []
    for attempt, buffer_deg in enumerate(DEM_BUFFERS_DEG):
        # Unique temp file per request — a shared fixed path would let two concurrent
        # requests overwrite each other's DEM mid-analysis.
        fd, dem_path = tempfile.mkstemp(prefix="point_dem_", suffix=".tif")
        os.close(fd)
        try:
            await fetch_dem_tile(lat, lon, buffer_deg=buffer_deg, out_path=dem_path)

            # delineate_catchment is CPU-bound (flow routing over the whole tile), so it
            # runs in a worker thread to keep the event loop responsive.
            try:
                result = await asyncio.to_thread(delineate_catchment, dem_path, lat, lon)
            except Exception as e:
                raise TerrainDataError(f"Catchment computation failed: {e}")
            polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])
        finally:
            try:
                os.remove(dem_path)
            except OSError:
                pass

        if not result["touches_edge"]:
            break
        if attempt == len(DEM_BUFFERS_DEG) - 1:
            warnings.append(TRUNCATED_WARNING)

    return TerrainResult(
        catchment_polygon=polygon,
        area_km2=result["area_km2"],
        avg_slope=result["avg_slope"],
    ), warnings


class TerrainDataError(Exception):
    """Raised when DEM fetch or catchment computation fails."""
    pass
