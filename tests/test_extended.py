"""
Extended testing suite — verifies edge cases, generalization, and new endpoints:
  1. Empty KML / zero-byte upload
  2. Malformed KML
  3. KMZ (zipped KML) contour file
  4. Land area selection endpoint (/api/analyze-area)
  5. Village search endpoint (/api/villages/search)
  6. Health monitoring endpoint (/api/health)
"""

import sys
import os
import io
import zipfile
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

client = TestClient(app)

SAMPLE_KML = os.path.join(os.path.dirname(__file__), "sample_data", "contours_1m.kml")


def test_rejects_empty_file():
    """Empty file upload should return 400 with a clean error message, not 500 crash."""
    empty_file = io.BytesIO(b"")
    resp = client.post(
        "/analyzeContour",
        files={"contour_map": ("empty.kml", empty_file, "application/vnd.google-earth.kml+xml")},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()
    print("✓ Correctly rejects an empty 0-byte KML file")


def test_rejects_malformed_xml():
    """Malformed XML should return 400, not an unhandled XMLSyntaxError."""
    bad_xml = io.BytesIO(b"<kml><unclosed_tag>broken</kml>")
    resp = client.post(
        "/analyzeContour",
        files={"contour_map": ("bad.kml", bad_xml, "application/vnd.google-earth.kml+xml")},
    )
    assert resp.status_code == 400
    assert "invalid kml/xml" in resp.json()["detail"].lower()
    print("✓ Correctly handles malformed XML syntax")


def test_parses_real_kmz():
    """Verifies that a zipped .kmz file is automatically unpacked and analyzed."""
    with open(SAMPLE_KML, "rb") as f:
        kml_content = f.read()

    # Create an in-memory zip archive with doc.kml inside
    kmz_buffer = io.BytesIO()
    with zipfile.ZipFile(kmz_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml_content)
    kmz_bytes = kmz_buffer.getvalue()

    resp = client.post(
        "/analyzeContour",
        files={"contour_map": ("sample_contours.kmz", io.BytesIO(kmz_bytes), "application/vnd.google-earth.kmz")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["contour_lines_parsed"] > 0
    assert data["catchment_area_km2"] > 0
    assert data["expected_water_volume_m3"] is not None
    assert data["expected_water_volume_m3"] > 0
    print(f"✓ KMZ file parsed and analyzed successfully (volume: {data['expected_water_volume_m3']} m3)")


def test_analyze_land_area_endpoint():
    """Verifies the Land Area Selection requirement (POST /api/analyze-area)."""
    payload = {
        "bounds": {
            "min_lat": 21.230,
            "max_lat": 21.250,
            "min_lon": 81.275,
            "max_lon": 81.295
        },
        "name": "Test Agricultural Sector"
    }
    resp = client.post("/api/analyze-area", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "suggested_pond_site" in data
    assert "lat" in data["suggested_pond_site"]
    assert "lon" in data["suggested_pond_site"]
    assert data["catchment_area_km2"] > 0
    assert data["expected_water_volume_m3"] > 0
    assert data["catchment_polygon"]["type"] in ("Polygon", "MultiPolygon")
    print(f"✓ Land area analyzed: suggested pond at ({data['suggested_pond_site']['lat']}, {data['suggested_pond_site']['lon']}), "
          f"volume: {data['expected_water_volume_m3']} m3")


def test_village_search_endpoint():
    """Verifies the village search endpoint (/api/villages/search)."""
    resp = client.get("/api/villages/search?q=Bhilai")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    found = any("Bhilai" in r["name"] for r in data["results"])
    assert found
    print(f"✓ Village search returned {len(data['results'])} results for 'Bhilai'")


def test_health_check_endpoint():
    """Verifies the system health endpoint (/api/health)."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["memory_mb"] > 0
    print(f"✓ Health check passed (memory: {data['memory_mb']} MB, uptime: {data['uptime_seconds']}s)")


if __name__ == "__main__":
    test_rejects_empty_file()
    test_rejects_malformed_xml()
    test_parses_real_kmz()
    test_analyze_land_area_endpoint()
    test_village_search_endpoint()
    test_health_check_endpoint()
    print("\nALL EXTENDED TESTS PASSED SUCCESSFULLY!")
