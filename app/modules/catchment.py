"""
Catchment delineation — the actual GIS/hydrology algorithm from the HLD.

This is REAL, tested logic (not a stub): given a DEM raster file and a pour point
(the candidate pond location), it runs:
  1. Fill depressions (removes noise/sinks that would break flow routing)
  2. Resolve flats (handles perfectly flat areas so flow direction is well-defined)
  3. D8 flow direction (which of 8 neighbors each cell drains into)
  4. Flow accumulation (how much upstream area flows through each cell)
  5. Catchment delineation (trace backward from the pour point to find all
     draining cells)
  6. Polygonize (convert the cell mask into an actual boundary shape)

Tested against a synthetic bowl-shaped DEM — see tests/test_terrain.py.
Swap in a real DEM file path (from dem_fetch.py) once network access is available.
"""

import numpy as np

# Compatibility shim: pysheds still calls the old np.in1d, which numpy 2.x removed
# in favor of np.isin. This is a library/numpy-version mismatch, not a design choice —
# leave this in until pysheds ships a numpy-2.x-compatible release.
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from pysheds.grid import Grid


def _prepare_flow_grid(dem_path: str):
    """
    Shared setup used by both delineate_catchment() (user-specified point) and
    find_pond_site() (auto-discovered point) — conditioning + D8 flow direction
    + accumulation only need to run ONCE per DEM, regardless of how many points
    get analyzed against it afterward.
    """
    grid = Grid.from_raster(dem_path)
    dem = grid.read_raster(dem_path)

    filled = grid.fill_depressions(dem)
    inflated = grid.resolve_flats(filled)
    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)

    return grid, dem, fdir, acc


def _pixel_size_meters(grid, at_lat: float) -> tuple[float, float]:
    """Converts this raster's degree-based pixel size to meters at a given latitude —
    same logic used consistently for both the OpenTopography path and the
    contour-derived path, since both DEMs are in geographic (degree) coordinates."""
    pixel_dx_deg = abs(grid.affine.a)
    pixel_dy_deg = abs(grid.affine.e)
    meters_per_degree_lat = 111_320
    meters_per_degree_lon = 111_320 * np.cos(np.radians(at_lat))
    return pixel_dx_deg * meters_per_degree_lon, pixel_dy_deg * meters_per_degree_lat


def _catchment_stats(grid, dem, catch, pour_lat: float) -> dict:
    """Area + average slope for a given catchment mask — shared by both entry points."""
    pixel_size_x_m, pixel_size_y_m = _pixel_size_meters(grid, pour_lat)
    pixel_area_m2 = pixel_size_x_m * pixel_size_y_m

    catchment_cells = int(np.sum(catch))
    area_km2 = catchment_cells * pixel_area_m2 / 1_000_000

    try:
        dem_arr = np.asarray(dem, dtype="float64")
        dzdy, dzdx = np.gradient(dem_arr, pixel_size_y_m, pixel_size_x_m)
        slope_pct = np.sqrt(dzdx ** 2 + dzdy ** 2) * 100
        avg_slope = float(np.nanmean(slope_pct[catch])) if np.any(catch) else 0.0
    except Exception:
        avg_slope = 0.0

    return {
        "area_km2": round(area_km2, 4),
        "avg_slope": round(avg_slope, 2),
        "pixel_size_m": float(np.sqrt(pixel_area_m2)),
    }


def delineate_catchment(dem_path: str, pour_lat: float, pour_lon: float) -> dict:
    """
    in  -> dem_path: path to a GeoTIFF DEM file
           pour_lat, pour_lon: the candidate pond location (where water should collect)
    out -> {
             "catchment_mask": bool ndarray (for internal use / area calc),
             "area_km2": float,
             "avg_slope": float,
             "pixel_size_m": float,
           }

    Unchanged behavior/signature from before this refactor — existing callers
    (terrain.py, tests/test_terrain.py) don't need to change.
    """
    grid, dem, fdir, acc = _prepare_flow_grid(dem_path)
    catch = grid.catchment(x=pour_lon, y=pour_lat, fdir=fdir, xytype="coordinate")
    stats = _catchment_stats(grid, dem, catch, pour_lat)

    return {
        "catchment_mask": catch,
        "grid": grid,
        "fdir": fdir,
        **stats,
    }


def find_pond_site(dem_path: str, border_margin_frac: float = 0.08) -> dict:
    """
    AUTOMATIC pond-site selection — the new piece needed for the contour-map
    phase, since there's no user-clicked point anymore. The system has to pick
    a location itself, purely from the DEM's own terrain — nothing hardcoded
    about any specific map.

    Approach: after running flow accumulation over the whole grid, the pixel
    with the HIGHEST accumulation is where the most water naturally converges —
    that's the standard GIS heuristic for "best drainage point" and a reasonable
    proxy for "good pond site." Pixels within border_margin_frac of the grid's
    edge are excluded from consideration, because accumulation is artificially
    inflated right at a DEM's boundary (water appears to "flow off the edge"
    into cells that don't really exist) — this is a known edge artifact in
    flow-accumulation analysis, not specific to this dataset.

    in  -> dem_path, border_margin_frac (fraction of width/height to exclude from each edge)
    out -> {
             "pour_lat": float, "pour_lon": float,   # the auto-selected site
             "catchment_mask": ..., "area_km2": ..., "avg_slope": ..., "pixel_size_m": ...,
             "grid": ..., "fdir": ...,
           }
    """
    grid, dem, fdir, acc = _prepare_flow_grid(dem_path)

    acc_arr = np.asarray(acc)
    n_rows, n_cols = acc_arr.shape
    margin_rows = max(int(n_rows * border_margin_frac), 1)
    margin_cols = max(int(n_cols * border_margin_frac), 1)

    # Mask out the border so the interior is all that's considered.
    interior_mask = np.zeros_like(acc_arr, dtype=bool)
    interior_mask[margin_rows:n_rows - margin_rows, margin_cols:n_cols - margin_cols] = True

    masked_acc = np.where(interior_mask, acc_arr, -np.inf)
    best_row, best_col = np.unravel_index(np.argmax(masked_acc), masked_acc.shape)

    # Convert the winning pixel's row/col back to real lon/lat using the raster's affine transform.
    pour_lon, pour_lat = grid.affine * (best_col, best_row)

    catch = grid.catchment(x=pour_lon, y=pour_lat, fdir=fdir, xytype="coordinate")
    stats = _catchment_stats(grid, dem, catch, pour_lat)

    return {
        "pour_lat": float(pour_lat),
        "pour_lon": float(pour_lon),
        "catchment_mask": catch,
        "grid": grid,
        "fdir": fdir,
        **stats,
    }


def catchment_to_geojson(grid, catch_mask) -> dict:
    """
    Converts the boolean catchment mask into a GeoJSON-style polygon (or multipolygon
    if the catchment isn't one connected blob — rare but possible on noisy DEMs).
    """
    shapes = list(grid.polygonize(catch_mask.astype("int32")))
    if not shapes:
        return {"type": "Polygon", "coordinates": []}

    # polygonize yields (geometry_dict, value) pairs — keep only the polygons
    # that correspond to "inside the catchment" (value == 1), not the background.
    polygons = [geom for geom, value in shapes if value == 1]

    if len(polygons) == 1:
        return polygons[0]
    return {"type": "MultiPolygon", "coordinates": [p["coordinates"] for p in polygons]}
