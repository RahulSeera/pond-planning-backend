"""
Recommendation Module — combines Terrain + Rainfall results into a runoff estimate
and pond sizing recommendation.

Unlike terrain.py / rainfall.py, this one is NOT a stub — the Rational Method formula
is simple enough to implement for real right away. This is your actual "AI/analysis"
logic in the HLD sense — the part worth explaining carefully in the demo.
"""

from app.schemas import TerrainResult, RainfallResult, RecommendationResult

# Runoff coefficient for rural/agricultural land cover on loamy soils — a typical
# textbook value (runoff-coefficient tables give roughly 0.2-0.5 for cultivated land).
# Future work: look this up from a land-cover/soil table instead of a constant.
RUNOFF_COEFFICIENT_C = 0.35

MIN_POND_DEPTH_M = 2.5
MAX_POND_DEPTH_M = 4.5
TARGET_CAPTURE_FRACTION = 0.7  # capture ~70% of estimated seasonal runoff


def recommend(terrain: TerrainResult, rainfall: RainfallResult) -> RecommendationResult:
    """
    Interface contract:
      in  -> TerrainResult (catchment area), RainfallResult (rainfall intensity)
      out -> RecommendationResult (runoff volume, pond depth/area/capacity, suitability score)

    Formula (volumetric form of the Rational Method): Q = C * I * A
      C = runoff coefficient (land-cover dependent)
      I = seasonal (June-September monsoon) rainfall DEPTH in meters, averaged over
          the years of archive data — so Q is a seasonal runoff VOLUME (m³), not the
          peak discharge (m³/s) the classical Rational Method computes from intensity.
      A = catchment area in m²
    """
    catchment_area_m2 = terrain.area_km2 * 1_000_000  # km² -> m²
    monsoon_rainfall_m = rainfall.seasonal.get("monsoon_mm", 0) / 1000  # mm -> m

    # Q = C * I * A  (I*A here in m^3 since rainfall depth * area = volume of rain falling)
    runoff_m3 = RUNOFF_COEFFICIENT_C * monsoon_rainfall_m * catchment_area_m2

    target_capacity_m3 = runoff_m3 * TARGET_CAPTURE_FRACTION

    # Pick a realistic depth:
    # Small catchments (<5,000 m³): 2.5m (anti-evaporation minimum depth)
    # Medium catchments (5,000 - 200,000 m³): scales progressively from 2.5m to 4.5m
    # Large catchments (>200,000 m³): 4.5m (structural limit for unlined earthen embankments)
    if target_capacity_m3 <= 5000:
        depth_m = MIN_POND_DEPTH_M
    elif target_capacity_m3 >= 200000:
        depth_m = MAX_POND_DEPTH_M
    else:
        fraction = (target_capacity_m3 - 5000) / 195000
        depth_m = round(MIN_POND_DEPTH_M + fraction * (MAX_POND_DEPTH_M - MIN_POND_DEPTH_M), 2)

    surface_area_m2 = target_capacity_m3 / depth_m if depth_m > 0 else 0

    # Suitability score (0-100) per HLD §3.5:
    # 1. Slope Score: optimal on gentle slopes (1-4%), penalized above 5% (excessive cut/fill & breach risk)
    if terrain.avg_slope <= 4.0:
        slope_score = 100.0
    else:
        slope_score = max(10.0, 100.0 - (terrain.avg_slope - 4.0) * 12.0)

    # 2. Catchment Adequacy: ideal (full score) between 0.5 km² and 5.0 km² for community
    #    pond harvesting. Piecewise-linear and continuous — no jumps at the breakpoints:
    #    < 0.1 km²   : 10 -> 50   (tiny catchment, pond unlikely to fill)
    #    0.1-0.5 km² : 50 -> 100  (ramping up to adequate)
    #    0.5-5.0 km² : 100        (optimal band)
    #    > 5.0 km²   : -3 per km², floor 50 (large inflow -> spillway/breach risk)
    area = terrain.area_km2
    if area < 0.1:
        catchment_score = 10.0 + (area / 0.1) * 40.0
    elif area < 0.5:
        catchment_score = 50.0 + ((area - 0.1) / 0.4) * 50.0
    elif area <= 5.0:
        catchment_score = 100.0
    else:
        catchment_score = max(50.0, 100.0 - (area - 5.0) * 3.0)

    # 3. Rainfall Reliability:
    annual_mm = rainfall.annual_avg_mm
    if annual_mm >= 1000.0:
        rainfall_score = 100.0
    elif annual_mm >= 500.0:
        rainfall_score = 60.0 + ((annual_mm - 500.0) / 500.0) * 40.0
    else:
        rainfall_score = max(15.0, (annual_mm / 500.0) * 60.0)

    # Weighted combination: 40% catchment adequacy, 35% slope suitability, 25% rainfall reliability
    raw_suitability = 0.40 * catchment_score + 0.35 * slope_score + 0.25 * rainfall_score
    suitability_score = round(max(5.0, min(98.0, raw_suitability)), 1)

    return RecommendationResult(
        runoff_m3=round(runoff_m3, 1),
        depth_m=depth_m,
        surface_area_m2=round(surface_area_m2, 1),
        capacity_m3=round(target_capacity_m3, 1),
        suitability_score=suitability_score,
    )

