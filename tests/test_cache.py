"""
Test for the caching layer — proves get/set work against real PostgreSQL,
and that TTL expiry is honored (an old entry is treated as a miss).

Run: python3 tests/test_cache.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from app.db.database import SessionLocal, engine, Base
from app.db import models
from app.db.cache import get_cached_response, set_cached_response, make_cache_key, CACHE_TTL_HOURS


def test_cache_miss_then_hit():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        lat, lon = 22.111, 82.222

        # ---- Miss: nothing cached yet ----
        result = get_cached_response(db, lat, lon)
        assert result is None, "Expected a cache miss for a location never queried before"
        print("✓ Cache miss confirmed for a fresh location")

        # ---- Write ----
        fake_response = {
            "request_id": 999, "lat": lat, "lon": lon,
            "terrain": {"catchment_polygon": {}, "area_km2": 1.2, "avg_slope": 3.4},
            "rainfall": {"annual_avg_mm": 1000.0, "seasonal": {}, "data_years": 10},
            "recommendation": {"runoff_m3": 500.0, "depth_m": 3.0, "surface_area_m2": 100.0,
                                "capacity_m3": 300.0, "suitability_score": 60.0},
            "warnings": [],
        }
        set_cached_response(db, lat, lon, fake_response)
        print("✓ Cache write succeeded")

        # ---- Hit: same location should now return the cached value ----
        result = get_cached_response(db, lat, lon)
        assert result is not None, "Expected a cache hit right after writing"
        assert result["terrain"]["area_km2"] == 1.2
        print("✓ Cache hit returns the correct stored value")

        # ---- Nearby-but-rounds-to-same-key location should also hit ----
        result_nearby = get_cached_response(db, lat + 0.0001, lon - 0.0001)
        assert result_nearby is not None, "A location rounding to the same key should also hit cache"
        print("✓ Nearby location (same rounded key) also hits cache")

    finally:
        # cleanup so repeated test runs don't accumulate stale rows
        db.query(models.QueryCache).filter(
            models.QueryCache.cache_key == make_cache_key(22.111, 82.222)
        ).delete()
        db.commit()
        db.close()


def test_ttl_expiry_treated_as_miss():
    db = SessionLocal()
    try:
        lat, lon = 23.333, 83.444
        key = make_cache_key(lat, lon)

        # Manually insert an entry with an old created_at, simulating an expired cache row
        old_time = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS + 1)
        entry = models.QueryCache(cache_key=key, response_json={"fake": "data"}, created_at=old_time)
        db.add(entry)
        db.commit()

        result = get_cached_response(db, lat, lon)
        assert result is None, "An entry older than CACHE_TTL_HOURS should be treated as a miss"
        print("✓ Expired cache entry correctly treated as a miss")

    finally:
        db.query(models.QueryCache).filter(models.QueryCache.cache_key == make_cache_key(23.333, 83.444)).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_cache_miss_then_hit()
    test_ttl_expiry_treated_as_miss()
    print("\nALL CHECKS PASSED — caching layer works correctly.")
