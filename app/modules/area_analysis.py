"""
Area Analysis Module — handles land area selection on the map.
Matches the professor's requirement:
  - An option to select the land area on a map
  - Generation of results based on the selected land area
  - Results include: Suggested pond location, Catchment area, Expected water volume that can be collected
  - Overlaid and visualized on the map
"""

import asyncio
import os
import tempfile
import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.schemas import BoundingBox, AreaAnalysisResponse, PondSite, TerrainResult, RainfallResult
from app.modules.catchment import find_pond_site, catchment_to_geojson
from app.modules.recommendation import recommend
from app.modules.rainfall import get_rainfall_stats, RainfallDataError, fallback_rainfall
from app.modules.dem_fetch import fetch_dem_tile
from app.heavy_jobs import run_heavy, ServerBusyError


def generate_terrain_for_bounds(bounds: BoundingBox, out_path: str, resolution: int = 150) -> str:
    """
    Generates a realistic synthetic topographic DEM for the given bounding box
    when external OpenTopography access is blocked or unavailable.
    Models natural topography with undulating valleys, ridges, and drainage channels.
    """
    n_lat = resolution
    n_lon = resolution

    lons = np.linspace(bounds.min_lon, bounds.max_lon, n_lon)
    lats = np.linspace(bounds.max_lat, bounds.min_lat, n_lat)  # descending for raster convention

    X, Y = np.meshgrid(np.linspace(0, 4 * np.pi, n_lon), np.linspace(0, 4 * np.pi, n_lat))
    
    # Natural valley gradient + sin/cos hills to produce a distinct drainage basin
    base_slope = (Y / (4 * np.pi)) * 25.0
    hills = np.sin(X) * np.cos(Y) * 12.0 + np.sin(2 * X + 0.5) * 6.0
    valley = -15.0 * np.exp(-((X - 2 * np.pi) ** 2) / 4.0)
    elevation = 280.0 + base_slope + hills + valley

    # n pixels exactly tiling the bounding box (elevation is a synthetic function of
    # the pixel index, so there is no separate sample-point grid to align with).
    pixel_size_lon = (bounds.max_lon - bounds.min_lon) / n_lon
    pixel_size_lat = (bounds.max_lat - bounds.min_lat) / n_lat
    transform = from_origin(bounds.min_lon, bounds.max_lat, pixel_size_lon, pixel_size_lat)

    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=n_lat,
        width=n_lon,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(elevation.astype("float32"), 1)

    return out_path


async def analyze_land_area(bounds: BoundingBox) -> AreaAnalysisResponse:
    """
    Analyzes the user-selected land area (bounding box):
      1. Obtains DEM for the area
      2. Computes D8 flow accumulation and finds the optimal pond site
      3. Traces catchment draining to this site
      4. Queries rainfall and calculates expected water volume (Rational Method)
      5. Generates pond sizing recommendations
    """
    warnings = []
    tmp_dir = tempfile.mkdtemp(prefix="area_dem_")
    tif_path = os.path.join(tmp_dir, "area_dem.tif")

    center_lat = (bounds.min_lat + bounds.max_lat) / 2.0
    center_lon = (bounds.min_lon + bounds.max_lon) / 2.0
    buffer_deg = max((bounds.max_lat - bounds.min_lat), (bounds.max_lon - bounds.min_lon)) / 2.0

    # 1. Fetch a real SRTM DEM tile covering the parcel plus a surrounding buffer
    #    (so the upstream catchment isn't truncated at the parcel edge), or fall
    #    back to synthetic terrain if OpenTopography is unreachable.
    try:
        await fetch_dem_tile(center_lat, center_lon, buffer_deg=max(buffer_deg + 0.01, 0.02), out_path=tif_path)
    except Exception as e:
        warnings.append(
            f"Real elevation data (OpenTopography SRTM) unavailable ({e}). Results below use "
            "SYNTHETIC demonstration terrain, not the actual land surface — do not use for site decisions."
        )
        generate_terrain_for_bounds(bounds, tif_path)

    # 2. Run flow accumulation & auto-discover pond site — restricted to cells INSIDE
    #    the selected parcel. CPU-bound, so it runs in a worker thread to keep the
    #    event loop (and the /api/health watchdog probe) responsive.
    search_bounds = (bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat)
    try:
        result = await run_heavy(find_pond_site, tif_path, 0.08, search_bounds)
    except ServerBusyError:
        raise
    except Exception as e:
        warnings.append(f"Terrain flow analysis failed ({e}); showing a rough whole-parcel estimate only.")
        # Fallback to center if terrain analysis fails
        pour_lat = center_lat
        pour_lon = center_lon
        area_km2 = round(((bounds.max_lat - bounds.min_lat) * 111.0) * ((bounds.max_lon - bounds.min_lon) * 111.0) * 0.45, 4)
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [bounds.min_lon, bounds.min_lat],
                [bounds.max_lon, bounds.min_lat],
                [bounds.max_lon, bounds.max_lat],
                [bounds.min_lon, bounds.max_lat],
                [bounds.min_lon, bounds.min_lat],
            ]]
        }
        result = {
            "pour_lat": pour_lat,
            "pour_lon": pour_lon,
            "area_km2": area_km2,
            "avg_slope": 3.8,
            "catchment_mask": None,
        }
    else:
        polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])
        if result.get("touches_edge"):
            warnings.append(
                "The catchment reaches the edge of the elevation tile, so the true upstream area "
                "may be larger than reported — treat catchment area and runoff as lower bounds."
            )
    finally:
        try:
            if os.path.exists(tif_path):
                os.remove(tif_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    pour_lat = result["pour_lat"]
    pour_lon = result["pour_lon"]
    area_km2 = result["area_km2"]
    avg_slope = result["avg_slope"]

    # 3. Query historical rainfall for the suggested pond site
    rainfall_result = None
    try:
        rainfall_result = await get_rainfall_stats(pour_lat, pour_lon)
    except RainfallDataError:
        rainfall_result, note = fallback_rainfall(pour_lat, pour_lon)
        warnings.append(note)

    # 4. Sizing & expected water volume calculation
    terrain_result = TerrainResult(
        catchment_polygon=polygon,
        area_km2=area_km2,
        avg_slope=avg_slope,
    )
    rec_result = recommend(terrain_result, rainfall_result)
    expected_water_volume = rec_result.runoff_m3

    return AreaAnalysisResponse(
        selected_bounds=bounds,
        suggested_pond_site=PondSite(lat=round(pour_lat, 6), lon=round(pour_lon, 6)),
        catchment_area_km2=round(area_km2, 4),
        avg_slope_percent=round(avg_slope, 2),
        catchment_polygon=polygon,
        expected_water_volume_m3=round(expected_water_volume, 1),
        rainfall=rainfall_result,
        recommendation=rec_result,
        warnings=warnings,
    )
