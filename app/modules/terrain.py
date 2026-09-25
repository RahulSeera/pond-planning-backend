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

from app.schemas import TerrainResult
from app.modules.dem_fetch import fetch_dem_tile
from app.modules.catchment import delineate_catchment, catchment_to_geojson


async def get_catchment(lat: float, lon: float) -> TerrainResult:
    """
    Interface contract:
      in  -> lat, lon of the selected point
      out -> TerrainResult with catchment polygon, area, and average slope

    Raises: TerrainDataError if the DEM can't be fetched/processed.
    """
    dem_path = await fetch_dem_tile(lat, lon)

    # delineate_catchment does the actual flow-accumulation work — this part
    # is CPU-bound, not I/O-bound, so it runs synchronously inside this async
    # function. For a heavier real DEM this could be moved to a thread pool
    # (asyncio.to_thread) so it doesn't block the event loop — worth doing
    # once you see real timing numbers.
    result = delineate_catchment(dem_path, pour_lat=lat, pour_lon=lon)

    polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])

    return TerrainResult(
        catchment_polygon=polygon,
        area_km2=result["area_km2"],
        avg_slope=result["avg_slope"],
    )


class TerrainDataError(Exception):
    """Raised when DEM fetch or catchment computation fails."""
    pass
