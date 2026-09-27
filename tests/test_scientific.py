"""
Regression tests for the scientific-correctness audit:
  - Rational-method unit conversions and 70% capture sizing
  - Depth bounds (2.5 m - 4.5 m) and monotonic depth scaling
  - Continuous suitability scoring with the 0.5-5.0 km² optimal catchment band
  - Real-SRTM-style int16 DEMs (with nodata) run through the flow pipeline
  - Land-area mode keeps the pond inside the user's parcel
  - Contour GeoTIFF pixel centers coincide with the interpolation sample points
"""

import os
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas import TerrainResult, RainfallResult
from app.modules.recommendation import recommend
from app.modules.catchment import find_pond_site, delineate_catchment, catchment_to_geojson
from app.modules.dem_from_contours import write_grid_to_geotiff


def _terrain(area_km2, slope=2.0):
    return TerrainResult(catchment_polygon={}, area_km2=area_km2, avg_slope=slope)


def _rain(monsoon_mm, annual_mm=None):
    return RainfallResult(
        annual_avg_mm=annual_mm if annual_mm is not None else monsoon_mm * 1.25,
        seasonal={"monsoon_mm": monsoon_mm, "non_monsoon_mm": monsoon_mm * 0.25},
        data_years=10,
    )


def test_rational_method_units_and_capture_fraction():
    # 1 km² × 1000 mm × C=0.35 -> 0.35 × 1.0 m × 1,000,000 m² = 350,000 m³
    rec = recommend(_terrain(1.0), _rain(1000.0))
    assert abs(rec.runoff_m3 - 350_000.0) < 0.1
    assert abs(rec.capacity_m3 - 245_000.0) < 0.1  # 70% capture
    assert abs(rec.surface_area_m2 - rec.capacity_m3 / rec.depth_m) < 1.0


def test_depth_bounded_and_monotonic():
    depths = [recommend(_terrain(a), _rain(900.0)).depth_m for a in np.linspace(0.001, 10.0, 60)]
    assert min(depths) >= 2.5 and max(depths) <= 4.5
    assert all(b >= a for a, b in zip(depths, depths[1:]))


def test_catchment_score_continuous_with_optimal_band():
    def score(area):
        # slope 2% and 1200 mm keep the other two factors at 100, isolating catchment adequacy
        return recommend(_terrain(area), _rain(1000.0, annual_mm=1200.0)).suitability_score

    # Optimal band 0.5-5.0 km² all score the same (capped at 98)
    assert score(0.5) == score(2.0) == score(5.0)
    # No jumps at breakpoints
    for bp in (0.1, 0.5, 5.0):
        assert abs(score(bp - 1e-6) - score(bp + 1e-6)) < 0.5
    # Tiny catchments are penalized
    assert score(0.05) < score(0.3) < score(1.0)


def _write_int16_bowl(path, nodata_corner=True):
    """SRTM-like tile: int16 elevations, -32768 nodata, a valley draining south."""
    n = 80
    y, x = np.mgrid[0:n, 0:n]
    elev = 300 - 0.5 * y + 0.02 * (x - n / 2) ** 2
    elev = elev.astype("int16")
    if nodata_corner:
        elev[:3, :3] = -32768
    transform = from_origin(81.25, 21.27, 1 / 3600, 1 / 3600)  # 1 arc-second like SRTMGL1
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1, dtype="int16",
                       crs="EPSG:4326", transform=transform, nodata=-32768) as dst:
        dst.write(elev, 1)
    return transform


def test_int16_srtm_style_dem_runs_through_pipeline():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "srtm_like.tif")
        _write_int16_bowl(path)
        result = find_pond_site(path)
        assert result["area_km2"] > 0
        geo = catchment_to_geojson(result["grid"], result["catchment_mask"])
        assert geo["type"] in ("Polygon", "MultiPolygon") and geo["coordinates"]

        point = delineate_catchment(path, result["pour_lat"], result["pour_lon"], snap_radius_cells=0)
        assert abs(point["area_km2"] - result["area_km2"]) < 1e-6


def test_area_mode_pond_stays_inside_parcel():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "srtm_like.tif")
        t = _write_int16_bowl(path, nodata_corner=False)
        # A parcel in the north-west quadrant, away from the global accumulation maximum
        min_lon, max_lat = t.c + 15 * t.a, t.f + 15 * t.e
        max_lon, min_lat = t.c + 35 * t.a, t.f + 35 * t.e
        result = find_pond_site(path, search_bounds=(min_lon, min_lat, max_lon, max_lat))
        assert min_lon <= result["pour_lon"] <= max_lon
        assert min_lat <= result["pour_lat"] <= max_lat


def test_contour_geotiff_pixel_centers_match_samples():
    lons = np.linspace(81.0, 81.1, 50)
    lats = np.linspace(21.2, 21.1, 30)
    grid_data = {
        "elevation_grid": np.zeros((30, 50), dtype="float32"),
        "lons": lons, "lats": lats,
        "bounds": (81.0, 81.1, 21.1, 21.2),
    }
    with tempfile.TemporaryDirectory() as d:
        path = write_grid_to_geotiff(grid_data, os.path.join(d, "g.tif"))
        with rasterio.open(path) as src:
            for row, col in [(0, 0), (29, 49), (12, 33)]:
                lon, lat = src.transform * (col + 0.5, row + 0.5)
                assert abs(lon - lons[col]) < 1e-9 and abs(lat - lats[row]) < 1e-9


def test_rainfall_circuit_breaker_skips_after_failure(monkeypatch):
    import asyncio
    import app.modules.rainfall as rainfall

    calls = []

    async def failing_fetch(lat, lon):
        calls.append(1)
        raise rainfall.RainfallDataError("network blocked")

    monkeypatch.setattr(rainfall, "fetch_historical_rainfall", failing_fetch)
    monkeypatch.setattr(rainfall, "_last_failure_at", None)
    for _ in range(3):
        try:
            asyncio.run(rainfall.get_rainfall_stats(21.24, 81.28))
        except rainfall.RainfallDataError:
            pass
    assert len(calls) == 1  # later requests go straight to the baseline


def test_bundled_rainfall_used_near_demo_site_baseline_elsewhere():
    from app.modules.rainfall import fallback_rainfall, CLIMATE_BASELINE

    near, note = fallback_rainfall(21.24171, 81.28692)  # contours_1m.kml pond site
    assert near.data_years == 10 and near.seasonal["monsoon_mm"] > 0
    assert "bundled Open-Meteo archive" in note

    far, note = fallback_rainfall(26.6, 75.1)  # Rajasthan, outside the bundled region
    assert far.seasonal["monsoon_mm"] == CLIMATE_BASELINE["seasonal"]["monsoon_mm"]
    assert "baseline" in note


def test_contour_demo_matches_live_rainfall_when_network_blocked(monkeypatch):
    """Simulates the campus container (Open-Meteo blocked): the reference contour
    run must still use the real archive figures via the bundled data."""
    from fastapi.testclient import TestClient
    import app.main as main
    import app.modules.rainfall as rainfall

    async def blocked(lat, lon):
        raise rainfall.RainfallDataError("network blocked")

    monkeypatch.setattr(rainfall, "fetch_historical_rainfall", blocked)
    monkeypatch.setattr(rainfall, "_last_failure_at", None)
    kml = os.path.join(os.path.dirname(__file__), "sample_data", "contours_1m.kml")
    with TestClient(main.app) as client, open(kml, "rb") as f:
        resp = client.post("/analyzeContour", files={"contour_map": ("contours_1m.kml", f, "application/xml")})
    data = resp.json()
    assert resp.status_code == 200
    assert data["rainfall"]["seasonal"]["monsoon_mm"] == 1251.4
    assert abs(data["expected_water_volume_m3"] - 1713241.7) < 1.0
    assert any("bundled Open-Meteo archive" in w for w in data["warnings"])


def test_heavy_jobs_never_overlap_and_queue_times_out(monkeypatch):
    """Admission control: on the 512 MiB / 1-CPU container, overlapping heavy jobs
    were OOM-killed, so at most one may run; a job that waits too long gets 503."""
    import asyncio
    import threading
    import time
    import app.heavy_jobs as hj

    active, peak = [0], [0]
    lock = threading.Lock()

    def slow_job():
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        return "done"

    async def run_three():
        return await asyncio.gather(*(hj.run_heavy(slow_job) for _ in range(3)))

    assert asyncio.run(run_three()) == ["done"] * 3
    assert peak[0] == 1

    monkeypatch.setattr(hj, "QUEUE_TIMEOUT_S", 0.05)

    async def overloaded():
        return await asyncio.gather(hj.run_heavy(slow_job), hj.run_heavy(slow_job), return_exceptions=True)

    results = asyncio.run(overloaded())
    assert results.count("done") == 1
    assert any(isinstance(r, hj.ServerBusyError) for r in results)
