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

from affine import Affine
from pysheds.grid import Grid
from pysheds.sview import Raster, ViewFinder


def _prepare_flow_grid(dem_path: str):
    """
    Shared setup used by both delineate_catchment() (user-specified point) and
    find_pond_site() (auto-discovered point) — conditioning + D8 flow direction
    + accumulation only need to run ONCE per DEM, regardless of how many points
    get analyzed against it afterward.

    Returns (grid, dem, fdir, acc, flow_grid):
      grid      -> the DEM's own geographic (EPSG:4326) grid; used for coordinates
                   and polygonization.
      flow_grid -> the same cells with a METRIC affine (pixel size in meters),
                   used for flow direction/accumulation/catchment tracing.

    Why a separate metric grid: pysheds' D8 divides the elevation drop by the
    cell spacing taken straight from the raster's affine. For a lat/lon raster
    that spacing is in degrees, where one degree of longitude is only
    cos(latitude) as long as one degree of latitude (~7% shorter at 21°N), so
    east-west slopes would be misjudged. Giving the flow grid the true
    Δx = Δλ·111,320·cos(φ), Δy = Δφ·111,320 spacing makes D8 compare real slopes.
    """
    grid = Grid.from_raster(dem_path)
    dem = grid.read_raster(dem_path)

    # SRTM GeoTIFFs store elevation as int16; pysheds' numba-compiled Priority-Flood
    # compiles reliably only for float32 input here (float64/int16 hit a numba
    # lowering error in _priority_flood). Normalize to float32 (nodata cells
    # become NaN) so real downloaded tiles and contour-derived float32 grids take
    # the exact same path.
    dem_arr = np.asarray(dem, dtype="float32")
    if dem.nodata is not None and not np.isnan(dem.nodata):
        dem_arr[dem_arr == dem.nodata] = np.nan
    float_vf = ViewFinder(affine=dem.affine, shape=dem.shape, nodata=np.float32(np.nan),
                          mask=dem.viewfinder.mask, crs=dem.crs)
    dem = Raster(dem_arr, viewfinder=float_vf)
    grid = Grid(viewfinder=float_vf)

    filled = grid.fill_depressions(dem)  # Priority-Flood (Barnes et al., 2014)
    inflated = grid.resolve_flats(filled)

    vf = grid.viewfinder
    n_rows = vf.shape[0]
    center_lat = vf.affine.f + vf.affine.e * n_rows / 2.0
    pixel_x_m, pixel_y_m = _pixel_size_meters(grid, center_lat)
    metric_vf = ViewFinder(
        affine=Affine(pixel_x_m, 0.0, 0.0, 0.0, -pixel_y_m, 0.0),
        shape=vf.shape, nodata=vf.nodata, mask=vf.mask, crs=vf.crs,
    )
    flow_grid = Grid(viewfinder=metric_vf)

    fdir = flow_grid.flowdir(Raster(np.asarray(inflated), viewfinder=metric_vf))
    acc = flow_grid.accumulation(fdir)

    return grid, dem, fdir, acc, flow_grid


def _cell_center_lonlat(grid, row: int, col: int) -> tuple[float, float]:
    """Geographic coordinates of a cell's CENTER (the affine maps integer indices to its top-left corner)."""
    lon, lat = grid.affine * (col + 0.5, row + 0.5)
    return float(lon), float(lat)


def _lonlat_to_cell(grid, lon: float, lat: float) -> tuple[int, int]:
    """Row/col of the cell containing (lon, lat); raises ValueError if the point is off the raster."""
    col_f, row_f = ~grid.affine * (lon, lat)
    row, col = int(np.floor(row_f)), int(np.floor(col_f))
    n_rows, n_cols = grid.viewfinder.shape
    if not (0 <= row < n_rows and 0 <= col < n_cols):
        raise ValueError(f"Point ({lat}, {lon}) lies outside the DEM extent.")
    return row, col


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
        dem_arr = np.asarray(dem, dtype="float32")
        dzdy, dzdx = np.gradient(dem_arr, pixel_size_y_m, pixel_size_x_m)
        slope_pct = np.sqrt(dzdx ** 2 + dzdy ** 2) * 100
        avg_slope = float(np.nanmean(slope_pct[catch])) if np.any(catch) else 0.0
    except Exception:
        avg_slope = 0.0

    # A catchment that reaches the raster border may continue beyond the DEM, so
    # its area is only a lower bound — callers use this to fetch a larger tile or warn.
    catch_arr = np.asarray(catch, dtype=bool)
    touches_edge = bool(catch_arr[0].any() or catch_arr[-1].any() or catch_arr[:, 0].any() or catch_arr[:, -1].any())

    return {
        "area_km2": round(float(area_km2), 4),
        "avg_slope": round(avg_slope, 2),
        "pixel_size_m": float(np.sqrt(pixel_area_m2)),
        "touches_edge": touches_edge,
    }


def delineate_catchment(dem_path: str, pour_lat: float, pour_lon: float, snap_radius_cells: int = 2) -> dict:
    """
    in  -> dem_path: path to a GeoTIFF DEM file
           pour_lat, pour_lon: the candidate pond location (where water should collect)
    out -> {
             "catchment_mask": bool ndarray (for internal use / area calc),
             "area_km2": float,
             "avg_slope": float,
             "pixel_size_m": float,
           }

    Pour-point snapping (standard GIS "Snap Pour Point" step): a clicked point is
    rarely exactly on the one-cell-wide D8 drainage line, and a point one cell off
    the channel traces only a tiny hillslope catchment. The pour point is moved to
    the highest-accumulation cell within snap_radius_cells (default 2 ≈ 60 m on
    SRTM 30 m) of the click. snap_radius_cells=0 disables snapping.
    """
    grid, dem, fdir, acc, flow_grid = _prepare_flow_grid(dem_path)
    row, col = _lonlat_to_cell(grid, pour_lon, pour_lat)
    if snap_radius_cells > 0:
        acc_arr = np.asarray(acc)
        r0, r1 = max(row - snap_radius_cells, 0), min(row + snap_radius_cells + 1, acc_arr.shape[0])
        c0, c1 = max(col - snap_radius_cells, 0), min(col + snap_radius_cells + 1, acc_arr.shape[1])
        window = acc_arr[r0:r1, c0:c1]
        dr, dc = np.unravel_index(np.nanargmax(window), window.shape)
        row, col = r0 + int(dr), c0 + int(dc)
    catch = np.asarray(flow_grid.catchment(x=col, y=row, fdir=fdir, xytype="index"), dtype=bool)
    stats = _catchment_stats(grid, dem, catch, pour_lat)

    return {
        "catchment_mask": catch,
        "grid": grid,
        "fdir": fdir,
        **stats,
    }


def find_pond_site(dem_path: str, border_margin_frac: float = 0.08, search_bounds=None) -> dict:
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

    search_bounds (optional, (min_lon, min_lat, max_lon, max_lat)): restricts the
    candidate cells to a sub-region — used by land-area selection so the pond is
    always placed INSIDE the parcel the user drew, while flow is still routed over
    the larger surrounding DEM so the upstream catchment isn't cut off at the parcel edge.

    in  -> dem_path, border_margin_frac (fraction of width/height to exclude from each edge),
           search_bounds
    out -> {
             "pour_lat": float, "pour_lon": float,   # the auto-selected site (cell center)
             "catchment_mask": ..., "area_km2": ..., "avg_slope": ..., "pixel_size_m": ...,
             "grid": ..., "fdir": ...,
           }
    """
    grid, dem, fdir, acc, flow_grid = _prepare_flow_grid(dem_path)

    acc_arr = np.asarray(acc)
    n_rows, n_cols = acc_arr.shape
    margin_rows = max(int(n_rows * border_margin_frac), 1)
    margin_cols = max(int(n_cols * border_margin_frac), 1)

    # Mask out the border so the interior is all that's considered.
    interior_mask = np.zeros_like(acc_arr, dtype=bool)
    interior_mask[margin_rows:n_rows - margin_rows, margin_cols:n_cols - margin_cols] = True

    if search_bounds is not None:
        min_lon, min_lat, max_lon, max_lat = search_bounds
        cols = np.arange(n_cols)
        rows = np.arange(n_rows)
        center_lons = grid.affine.c + (cols + 0.5) * grid.affine.a
        center_lats = grid.affine.f + (rows + 0.5) * grid.affine.e
        in_bounds = np.outer(
            (center_lats >= min_lat) & (center_lats <= max_lat),
            (center_lons >= min_lon) & (center_lons <= max_lon),
        )
        # Only apply if the parcel actually overlaps the DEM's usable interior;
        # otherwise fall back to the plain interior search rather than failing.
        if np.any(interior_mask & in_bounds):
            interior_mask &= in_bounds

    masked_acc = np.where(interior_mask, acc_arr, -np.inf)
    best_row, best_col = np.unravel_index(np.argmax(masked_acc), masked_acc.shape)

    # Report the CENTER of the winning cell in real lon/lat.
    pour_lon, pour_lat = _cell_center_lonlat(grid, best_row, best_col)

    catch = np.asarray(flow_grid.catchment(x=int(best_col), y=int(best_row), fdir=fdir, xytype="index"), dtype=bool)
    stats = _catchment_stats(grid, dem, catch, pour_lat)

    return {
        "pour_lat": pour_lat,
        "pour_lon": pour_lon,
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
    # Re-attach the geographic grid's georeferencing so polygon vertices come out in lon/lat.
    mask_vf = ViewFinder(affine=grid.affine, shape=grid.viewfinder.shape, nodata=0, crs=grid.crs)
    mask_raster = Raster(np.asarray(catch_mask).astype("int32"), viewfinder=mask_vf)
    shapes = list(grid.polygonize(mask_raster))
    if not shapes:
        return {"type": "Polygon", "coordinates": []}

    # polygonize yields (geometry_dict, value) pairs — keep only the polygons
    # that correspond to "inside the catchment" (value == 1), not the background.
    polygons = [geom for geom, value in shapes if value == 1]

    if len(polygons) == 1:
        return polygons[0]
    return {"type": "MultiPolygon", "coordinates": [p["coordinates"] for p in polygons]}
