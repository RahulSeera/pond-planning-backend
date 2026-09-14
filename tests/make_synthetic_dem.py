"""
Generates a synthetic bowl-shaped DEM GeoTIFF for testing catchment delineation
without needing real OpenTopography network access.

FIXED: originally this used pixel_size=30 as if it were meters, while declaring
crs="EPSG:4326" (a geographic/degree-based CRS) - an inconsistency that hid the
degree-vs-meters unit bug until real DEM data exposed it. Now pixel size is
correctly specified in degrees (~0.00028 deg ~= 30m at typical latitudes),
matching what a real SRTM download actually looks like.

Run: python3 tests/make_synthetic_dem.py
Produces: tests/synthetic_dem.tif
"""

import numpy as np
import rasterio
from rasterio.transform import from_origin

# ~30m in degrees at mid-latitudes. Real SRTM pixels are ~0.000277778 deg (1 arc-second).
PIXEL_SIZE_DEG = 0.000277778


def make_bowl_dem(path: str, size: int = 200, pixel_size_deg: float = PIXEL_SIZE_DEG,
                   origin_lon: float = 81.55, origin_lat: float = 21.25):
    """
    size=200 gives a ~0.055 degree (~6km) box, roughly matching a real DEM tile
    from dem_fetch.py's buffer_deg=0.05 setting.
    """
    y, x = np.mgrid[0:size, 0:size]
    cx, cy = size * 0.7, size * 0.7  # low point (pour point) location in pixel coords
    dem = ((x - cx) ** 2 + (y - cy) ** 2).astype("float32") * 0.05 + 100

    transform = from_origin(origin_lon, origin_lat, pixel_size_deg, pixel_size_deg)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999,
    ) as dst:
        dst.write(dem, 1)

    pour_lon, pour_lat = transform * (cx, cy)
    return pour_lat, pour_lon


if __name__ == "__main__":
    pour_lat, pour_lon = make_bowl_dem("tests/synthetic_dem.tif")
    print(f"Synthetic DEM written to tests/synthetic_dem.tif")
    print(f"Pour point coordinates: lat={pour_lat}, lon={pour_lon}")
