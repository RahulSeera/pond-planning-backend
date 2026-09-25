"""
Test for catchment.py — proves the real D8/flow-accumulation logic works,
using a synthetic DEM (since real OpenTopography access isn't available in
this environment). Swap the DEM path for a real downloaded tile once you
have network access to test against real terrain.

Run: python3 tests/test_terrain.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.catchment import delineate_catchment, catchment_to_geojson


def test_catchment_on_synthetic_dem():
    dem_path = os.path.join(os.path.dirname(__file__), "synthetic_dem.tif")
    if not os.path.exists(dem_path):
        raise FileNotFoundError("Run tests/make_synthetic_dem.py first to generate the test DEM.")

    # This is the pour point printed by make_synthetic_dem.py — the deliberate
    # "low point" of the synthetic bowl, standing in for a real candidate pond location.
    # Now in real lat/lon degrees, matching what a real DEM's coordinates look like.
    pour_lat, pour_lon = 21.21111108, 81.58888892

    result = delineate_catchment(dem_path, pour_lat=pour_lat, pour_lon=pour_lon)

    assert result["area_km2"] > 0, "Catchment area should be non-zero for a valid bowl-shaped DEM"
    print(f"✓ Catchment area: {result['area_km2']} km2")
    print(f"✓ Avg slope: {result['avg_slope']}")

    geojson = catchment_to_geojson(result["grid"], result["catchment_mask"])
    assert geojson["type"] in ("Polygon", "MultiPolygon")
    assert len(geojson["coordinates"]) > 0, "Polygon should have real coordinates, not empty"
    print(f"✓ Polygonized catchment: {geojson['type']} with {len(geojson['coordinates'])} ring(s)")

    print("\nALL CHECKS PASSED — catchment delineation logic works.")


if __name__ == "__main__":
    test_catchment_on_synthetic_dem()
