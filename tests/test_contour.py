"""
Test for the contour-map phase — proves the full pipeline (parse KML -> interpolate
grid -> write GeoTIFF -> auto-select pond site -> catchment stats) works against the
REAL sample file provided for this assignment phase, both at the module level and
through the actual HTTP endpoint.

Run: python3 tests/test_contour.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_KML = os.path.join(os.path.dirname(__file__), "sample_data", "contours_1m.kml")


def test_parser_extracts_real_contours():
    from app.modules.kml_parser import parse_contours

    with open(SAMPLE_KML, "rb") as f:
        file_bytes = f.read()

    contours = parse_contours(file_bytes, "contours_1m.kml")

    assert len(contours) > 0, "Should parse at least one contour line from the real sample file"
    elevations = [c["elevation"] for c in contours]
    assert min(elevations) < max(elevations), "Sample file should have a real elevation range, not a flat map"
    print(f"✓ Parsed {len(contours)} contour lines, elevation range {min(elevations)}-{max(elevations)}m")


def test_interpolation_produces_full_grid():
    from app.modules.kml_parser import parse_contours
    from app.modules.dem_from_contours import contours_to_grid
    import numpy as np

    with open(SAMPLE_KML, "rb") as f:
        contours = parse_contours(f.read(), "contours_1m.kml")

    grid_data = contours_to_grid(contours)
    elevation_grid = grid_data["elevation_grid"]

    assert not np.isnan(elevation_grid).any(), "Interpolated grid should have no gaps (NaN cells)"
    assert elevation_grid.shape[0] > 1 and elevation_grid.shape[1] > 1
    print(f"✓ Interpolated a {elevation_grid.shape} grid with no gaps")


def test_full_pipeline_finds_a_real_pond_site():
    """
    This is the real end-to-end proof: KML -> grid -> GeoTIFF -> D8 flow analysis
    -> auto-selected pond site -> catchment stats, entirely derived from the file's
    own terrain — nothing about the result is hardcoded.
    """
    import tempfile
    from app.modules.kml_parser import parse_contours
    from app.modules.dem_from_contours import contours_to_grid, write_grid_to_geotiff
    from app.modules.catchment import find_pond_site, catchment_to_geojson

    with open(SAMPLE_KML, "rb") as f:
        contours = parse_contours(f.read(), "contours_1m.kml")

    grid_data = contours_to_grid(contours)

    with tempfile.TemporaryDirectory() as tmpdir:
        tif_path = os.path.join(tmpdir, "test_dem.tif")
        write_grid_to_geotiff(grid_data, tif_path)

        result = find_pond_site(tif_path)

        # Sanity bounds: the suggested site must fall within the actual contour
        # map's bounding box — proves it's derived from the file, not hardcoded.
        min_lon, max_lon, min_lat, max_lat = grid_data["bounds"]
        assert min_lon <= result["pour_lon"] <= max_lon
        assert min_lat <= result["pour_lat"] <= max_lat
        assert result["area_km2"] > 0, "Should find a real, non-zero catchment on this terrain"

        polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])
        assert polygon["type"] in ("Polygon", "MultiPolygon")
        assert len(polygon["coordinates"]) > 0

        print(f"✓ Auto-selected pond site: lat={result['pour_lat']:.5f}, lon={result['pour_lon']:.5f}")
        print(f"✓ Catchment area: {result['area_km2']} km2, avg slope: {result['avg_slope']}%")
        print(f"✓ Polygon generated with {len(polygon['coordinates'])} ring(s)")


def test_http_endpoint_end_to_end():
    """The real proof for the report/demo: an actual HTTP POST with a file upload,
    hitting the real /analyzeContour route, not just calling functions directly."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with open(SAMPLE_KML, "rb") as f:
        resp = client.post(
            "/analyzeContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
        )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["contour_lines_parsed"] > 0
    assert data["catchment_area_km2"] > 0
    assert "lat" in data["suggested_pond_site"]
    assert "lon" in data["suggested_pond_site"]
    assert data["catchment_polygon"]["type"] in ("Polygon", "MultiPolygon")

    print(f"✓ HTTP endpoint returned 200 with a real analysis: "
          f"{data['catchment_area_km2']} km2 catchment at "
          f"({data['suggested_pond_site']['lat']:.5f}, {data['suggested_pond_site']['lon']:.5f})")


def test_rejects_non_kml_files():
    """Basic input validation — a non-KML upload should fail cleanly, not crash."""
    from fastapi.testclient import TestClient
    from app.main import app
    import io

    client = TestClient(app)
    fake_file = io.BytesIO(b"this is not a kml file")

    resp = client.post(
        "/analyzeContour",
        files={"contour_map": ("not_a_contour.txt", fake_file, "text/plain")},
    )
    assert resp.status_code == 400, "Should reject non-.kml/.kmz files with a clean 400, not crash"
    print("✓ Correctly rejects a non-KML file upload")


if __name__ == "__main__":
    test_parser_extracts_real_contours()
    test_interpolation_produces_full_grid()
    test_full_pipeline_finds_a_real_pond_site()
    test_http_endpoint_end_to_end()
    test_rejects_non_kml_files()
    print("\nALL CHECKS PASSED — contour-map pipeline works end to end against the real sample file.")
