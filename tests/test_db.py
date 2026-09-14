"""
Test for the database layer — proves crud.py actually writes to and reads from
a REAL PostgreSQL + PostGIS database (not mocked). Requires Postgres running
and DATABASE_URL pointing at it (see app/db/database.py for the default).

Run: python3 tests/test_db.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal, engine, Base
from app.db import models, crud
from app.schemas import TerrainResult, RainfallResult, RecommendationResult


def test_full_analysis_round_trip():
    Base.metadata.create_all(bind=engine)  # safe to call repeatedly, no-op if tables exist
    db = SessionLocal()

    try:
        # ---- Write: create a request + all 3 result types ----
        req = crud.create_analysis_request(db, lat=21.2, lon=81.6)
        assert req.id is not None, "AnalysisRequest should get an auto-generated id"
        print(f"✓ Created AnalysisRequest id={req.id}")

        terrain = TerrainResult(
            catchment_polygon={
                "type": "Polygon",
                "coordinates": [[[81.59, 21.19], [81.61, 21.19], [81.61, 21.21], [81.59, 21.21], [81.59, 21.19]]],
            },
            area_km2=2.4,
            avg_slope=4.8,
        )
        crud.save_terrain_result(db, req.id, terrain)
        print("✓ Saved TerrainResult")

        rainfall = RainfallResult(
            annual_avg_mm=1120.0,
            seasonal={"monsoon_mm": 850.0, "non_monsoon_mm": 270.0},
            data_years=10,
        )
        crud.save_rainfall_result(db, req.id, rainfall)
        print("✓ Saved RainfallResult")

        rec = RecommendationResult(
            runoff_m3=15000.0, depth_m=3.0, surface_area_m2=5000.0,
            capacity_m3=15000.0, suitability_score=78.5,
        )
        crud.save_recommendation(db, req.id, rec)
        print("✓ Saved PondRecommendation")

        # ---- Read back: confirm everything round-trips correctly ----
        fetched = crud.get_analysis_by_id(db, req.id)
        assert fetched is not None, "Should be able to fetch the request back by id"
        assert fetched.terrain_result.area_km2 == 2.4
        assert fetched.rainfall_result.annual_avg_mm == 1120.0
        assert fetched.recommendation.suitability_score == 78.5
        print(f"✓ Read back full analysis for request id={fetched.id} — all values match")

        print("\nALL CHECKS PASSED — database layer works against real PostgreSQL+PostGIS.")

    finally:
        db.close()


if __name__ == "__main__":
    test_full_analysis_round_trip()
