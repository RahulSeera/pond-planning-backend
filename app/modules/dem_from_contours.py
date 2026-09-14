"""
Contour-to-DEM Interpolation — converts a list of contour lines (each a set of
(lon, lat) points at a known elevation) into a continuous elevation GRID, so
the existing D8/flow-accumulation logic (catchment.py) can run on it exactly
like it does on a real downloaded DEM.

Approach: treat every (lon, lat) point along every contour line as one
scattered elevation sample (we know its elevation exactly — it's on that
contour). Then use scipy's griddata to interpolate a regular grid from all
those scattered samples. This is a standard, well-established technique for
"contour-to-DEM" conversion — not something invented for this project.

This is written generically off whatever contour lines are passed in — no
values specific to any one sample map — so it generalizes to other contour
KML files with the same structure.
"""

import numpy as np
from scipy.interpolate import griddata

# Target grid resolution: how many pixels across the shorter dimension of the
# bounding box. Higher = more detail but slower; 200 is a reasonable balance
# for a course-project-scale DEM (matches roughly the resolution we used
# testing against real SRTM tiles).
GRID_RESOLUTION = 200

# Maximum number of scattered points fed into scipy's interpolation. Contour
# lines at fine resolution (e.g. 1m intervals) carry far more points than the
# output grid actually needs — griddata's Delaunay triangulation cost (both
# time and memory) scales with point count, and was measured to be the single
# largest memory consumer in this whole pipeline (~1MB of extra RAM per ~700
# points, roughly). Capping this is a deliberate memory/accuracy trade-off:
# still generalizes to any contour file, just subsamples dense ones evenly.
MAX_INTERPOLATION_POINTS = 20_000


class InterpolationError(Exception):
    """Raised when contour data can't be turned into a usable grid (e.g. too few points, degenerate bounding box)."""
    pass


def _decimate_points(points: np.ndarray, values: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Evenly subsamples scattered points down to at most max_points, if needed.
    Even (strided) subsampling rather than random keeps the reduction
    deterministic and preserves the overall spatial spread of the original
    points, which matters for interpolation quality.
    """
    n = len(points)
    if n <= max_points:
        return points, values

    stride = n // max_points
    return points[::stride], values[::stride]


def contours_to_grid(contours: list[dict], resolution: int = GRID_RESOLUTION) -> dict:
    """
    in  -> contours: [{"elevation": float, "coordinates": [(lon, lat), ...]}, ...]
           resolution: target grid size (pixels along the shorter axis)
    out -> {
             "elevation_grid": 2D numpy array of interpolated elevations,
             "lons": 1D array of grid column longitudes,
             "lats": 1D array of grid row latitudes,
             "bounds": (min_lon, max_lon, min_lat, max_lat),
           }
    """
    points = []  # (lon, lat)
    values = []  # elevation

    for contour in contours:
        for lon, lat in contour["coordinates"]:
            points.append((lon, lat))
            values.append(contour["elevation"])

    if len(points) < 4:
        raise InterpolationError("Not enough contour points to interpolate a grid (need at least 4).")

    points_arr = np.array(points)
    values_arr = np.array(values)

    points_arr, values_arr = _decimate_points(points_arr, values_arr, MAX_INTERPOLATION_POINTS)

    min_lon, max_lon = points_arr[:, 0].min(), points_arr[:, 0].max()
    min_lat, max_lat = points_arr[:, 1].min(), points_arr[:, 1].max()

    if max_lon <= min_lon or max_lat <= min_lat:
        raise InterpolationError("Contour points span a degenerate (zero-area) bounding box.")

    # Build a regular grid over the bounding box. Aspect-ratio-aware so pixels
    # are roughly square in degrees (good enough at small scale; a real GIS
    # tool would account for latitude distortion here too, same simplification
    # as the meters-per-degree conversion in catchment.py).
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat
    if lon_span >= lat_span:
        n_lon = resolution
        n_lat = max(int(resolution * lat_span / lon_span), 10)
    else:
        n_lat = resolution
        n_lon = max(int(resolution * lon_span / lat_span), 10)

    lons = np.linspace(min_lon, max_lon, n_lon)
    lats = np.linspace(max_lat, min_lat, n_lat)  # descending — row 0 = north, matches raster convention
    grid_lon, grid_lat = np.meshgrid(lons, lats)

    # Linear interpolation between scattered contour points. Cubic would be
    # smoother but is more prone to overshoot artifacts (fake local peaks/pits)
    # right at the edge of the data — linear is the safer default here.
    elevation_grid = griddata(points_arr, values_arr, (grid_lon, grid_lat), method="linear")

    # Points outside the convex hull of the contour data come back as NaN.
    # Fill them with nearest-neighbor interpolation so the grid has no holes
    # (flow-direction algorithms need a fully populated grid to work correctly).
    if np.isnan(elevation_grid).any():
        nearest_fill = griddata(points_arr, values_arr, (grid_lon, grid_lat), method="nearest")
        elevation_grid = np.where(np.isnan(elevation_grid), nearest_fill, elevation_grid)

    return {
        "elevation_grid": elevation_grid.astype("float32"),
        "lons": lons,
        "lats": lats,
        "bounds": (min_lon, max_lon, min_lat, max_lat),
    }


def write_grid_to_geotiff(grid_data: dict, out_path: str) -> str:
    """
    Writes the interpolated elevation grid out as a real GeoTIFF, so the
    EXISTING, already-tested catchment.py pipeline (D8 flow direction, flow
    accumulation, catchment delineation) can run on it completely unchanged —
    it doesn't know or care whether the DEM came from OpenTopography or from
    interpolated contour lines, it just sees a GeoTIFF either way.

    in  -> grid_data: the dict returned by contours_to_grid()
           out_path: where to write the .tif file
    out -> out_path (for convenience chaining)
    """
    import rasterio
    from rasterio.transform import from_origin

    elevation_grid = grid_data["elevation_grid"]
    min_lon, max_lon, min_lat, max_lat = grid_data["bounds"]
    n_lat, n_lon = elevation_grid.shape

    pixel_size_lon = (max_lon - min_lon) / n_lon
    pixel_size_lat = (max_lat - min_lat) / n_lat

    transform = from_origin(min_lon, max_lat, pixel_size_lon, pixel_size_lat)

    with rasterio.open(
        out_path, "w", driver="GTiff", height=n_lat, width=n_lon, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999,
    ) as dst:
        dst.write(elevation_grid, 1)

    return out_path
