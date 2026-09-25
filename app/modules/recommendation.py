"""
Recommendation Module — combines Terrain + Rainfall results into a runoff estimate
and pond sizing recommendation.

Unlike terrain.py / rainfall.py, this one is NOT a stub — the Rational Method formula
is simple enough to implement for real right away. This is your actual "AI/analysis"
logic in the HLD sense — the part worth explaining carefully in the demo.
"""

from app.schemas import TerrainResult, RainfallResult, RecommendationResult

# Runoff coefficient for rural/agricultural land cover (rough standard value).
# Real version: look this up from a small land-cover table instead of a constant.
RUNOFF_COEFFICIENT_C = 0.35

MIN_POND_DEPTH_M = 2.5
MAX_POND_DEPTH_M = 4.5
TARGET_CAPTURE_FRACTION = 0.7  # capture ~70% of estimated seasonal runoff


def recommend(terrain: TerrainResult, rainfall: RainfallResult) -> RecommendationResult:
    """
    Interface contract:
      in  -> TerrainResult (catchment area), RainfallResult (rainfall intensity)
      out -> RecommendationResult (runoff volume, pond depth/area/capacity, suitability score)

    Formula (Rational Method): Q = C * I * A
      C = runoff coefficient (land-cover dependent)
      I = rainfall intensity, approximated here from seasonal (monsoon) rainfall
      A = catchment area
    """
    catchment_area_m2 = terrain.area_km2 * 1_000_000  # km² -> m²
    monsoon_rainfall_m = rainfall.seasonal.get("monsoon_mm", 0) / 1000  # mm -> m

    # Q = C * I * A  (I*A here in m^3 since rainfall depth * area = volume of rain falling)
    runoff_m3 = RUNOFF_COEFFICIENT_C * monsoon_rainfall_m * catchment_area_m2

    target_capacity_m3 = runoff_m3 * TARGET_CAPTURE_FRACTION

    # Pick a depth within realistic bounds, solve for surface area.
    depth_m = MIN_POND_DEPTH_M if target_capacity_m3 < 5000 else MAX_POND_DEPTH_M
    surface_area_m2 = target_capacity_m3 / depth_m if depth_m > 0 else 0

    # Suitability score: simple weighted heuristic (slope + catchment adequacy).
    # TODO: refine — currently just a placeholder scoring shape.
    slope_score = max(0, 100 - terrain.avg_slope * 5)
    catchment_score = min(100, terrain.area_km2 * 20)
    suitability_score = round((slope_score + catchment_score) / 2, 1)

    return RecommendationResult(
        runoff_m3=round(runoff_m3, 1),
        depth_m=depth_m,
        surface_area_m2=round(surface_area_m2, 1),
        capacity_m3=round(target_capacity_m3, 1),
        suitability_score=suitability_score,
    )
