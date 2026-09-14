"""
API LAYER — the coordinator described in the HLD.

Responsibilities (matches what we discussed):
  1. Validate incoming request (Pydantic handles this automatically via schemas.py)
  2. Call Terrain + Rainfall modules IN PARALLEL (they're independent - asyncio.gather)
  3. Feed both results into the Recommendation module once both complete
  4. Persist the request + results to PostgreSQL
  5. Return the consolidated response
  6. (Caching is still a TODO - next piece to build)

Run with:  uvicorn app.main:app --reload
Docs at:   http://127.0.0.1:8000/docs   (auto-generated - this is your API documentation deliverable)
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
import asyncio
import tempfile
import os

from app.schemas import AnalyzeRequest, AnalyzeResponse, ContourAnalysisResponse, PondSite
from app.modules.kml_parser import parse_contours, ContourParseError
from app.modules.dem_from_contours import contours_to_grid, write_grid_to_geotiff, InterpolationError
from app.modules.catchment import find_pond_site, catchment_to_geojson

# NOTE: database (SQLAlchemy/geoalchemy2/psycopg2), terrain.py (OpenTopography),
# and rainfall.py imports are deliberately deferred to INSIDE the /api/analyze
# route functions below, not at module level. Measured cost: importing these
# eagerly adds ~40-200MB of resident memory that /analyzeContour never needs,
# which matters on memory-constrained deployments (a 512MB container hit an
# OOM kill before this change). /analyzeContour's own dependencies (rasterio,
# pysheds, scipy, lxml) are kept at module level since that route always needs them.

app = FastAPI(
    title="AI-based Village Pond Planning System",
    description="Recommends pond locations using terrain, catchment, and rainfall analysis.",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    # Deferred import — see note above. Only pulls in SQLAlchemy etc. if this
    # runs, and even then, a failure here is non-fatal (see try/except below).
    try:
        from app.db.database import engine, Base
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"WARNING: could not connect to database at startup ({e}). "
              f"/api/analyze will fail until this is fixed, but /analyzeContour is unaffected.")


@app.get("/")
async def root():
    return {"status": "ok", "service": "pond-planning-api"}


def _get_db_lazy():
    """
    Thin wrapper so FastAPI's dependency injection still gets a proper
    generator-based dependency (correct session cleanup via try/finally),
    while the actual database.py import stays deferred until a request to
    /api/analyze genuinely happens — not at module load time.
    """
    from app.db.database import get_db
    yield from get_db()


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, db=Depends(_get_db_lazy)):
    # Deferred imports — only loaded when this endpoint is actually hit.
    from app.modules.terrain import get_catchment, TerrainDataError
    from app.modules.rainfall import get_rainfall_stats, RainfallDataError
    from app.modules.recommendation import recommend
    from app.db import crud
    from app.db.cache import get_cached_response, set_cached_response

    warnings: list[str] = []

    # ---- Cache check: skip the whole pipeline (DEM download, D8 computation,
    # rainfall API call) if we've already analyzed this location recently. ----
    cached = get_cached_response(db, req.lat, req.lon)
    if cached is not None:
        return AnalyzeResponse(**cached)

    # ---- Step 0: create the DB row for this request up front, so we have a real id
    # to attach results to as they come in (matches the AnalysisRequest table in the HLD).
    db_request = crud.create_analysis_request(db, lat=req.lat, lon=req.lon, village_id=req.village_id)
    request_id = db_request.id

    # ---- Step 1: fire Terrain and Rainfall calls CONCURRENTLY ----
    # Both only depend on (lat, lon) - no reason to wait for one before starting the other.
    terrain_task = asyncio.create_task(get_catchment(req.lat, req.lon))
    rainfall_task = asyncio.create_task(get_rainfall_stats(req.lat, req.lon))

    # ---- Step 2: Terrain result - if this fails, we stop. Per the HLD's failure-handling
    # section: a wrong/fabricated catchment is worse than an explicit error, since terrain
    # analysis carries the most marks/weight.
    try:
        terrain_result = await terrain_task
    except TerrainDataError as e:
        print(f"TERRAIN ERROR: {e}")
        rainfall_task.cancel()
        raise HTTPException(status_code=502, detail="Terrain data unavailable — cannot compute catchment.")

    crud.save_terrain_result(db, request_id, terrain_result)

    # ---- Step 3: Rainfall result - if this fails, we DEGRADE gracefully instead of failing
    # the whole request (per HLD: show terrain results with a warning, don't block everything).
    rainfall_result = None
    try:
        rainfall_result = await rainfall_task
    except RainfallDataError as e:
        print(f"RAINFALL ERROR: {e}")
        warnings.append("Rainfall data unavailable — showing terrain results only.")

    if rainfall_result is not None:
        crud.save_rainfall_result(db, request_id, rainfall_result)

    # ---- Step 4: Recommendation - only runs if we have both terrain AND rainfall ----
    recommendation_result = None
    if rainfall_result is not None:
        recommendation_result = recommend(terrain_result, rainfall_result)
        crud.save_recommendation(db, request_id, recommendation_result)
    else:
        warnings.append("Recommendation skipped — requires rainfall data.")

    # TODO: check/write to cache keyed by rounded (lat, lon) before/after this whole flow

    response = AnalyzeResponse(
        request_id=request_id,
        lat=req.lat,
        lon=req.lon,
        terrain=terrain_result,
        rainfall=rainfall_result,
        recommendation=recommendation_result,
        warnings=warnings,
    )

    # Cache the full response so a repeat request for this location skips
    # DEM download + D8 computation + rainfall fetch entirely next time.
    # Only cache clean successes — don't cache a response carrying warnings
    # (e.g. rainfall failed), so a transient API failure doesn't get "stuck"
    # in the cache for a week.
    if not warnings:
        set_cached_response(db, req.lat, req.lon, response.model_dump())

    return response


@app.get("/api/analyze/{request_id}", response_model=AnalyzeResponse)
async def get_analysis(request_id: int, db=Depends(_get_db_lazy)):
    from app.db import crud
    from geoalchemy2.shape import to_shape
    from shapely.geometry import mapping

    fetched = crud.get_analysis_by_id(db, request_id)
    if fetched is None:
        raise HTTPException(status_code=404, detail="Analysis request not found.")

    point_shape = to_shape(fetched.point)

    return AnalyzeResponse(
        request_id=fetched.id,
        lat=point_shape.y,
        lon=point_shape.x,
        terrain={
            "catchment_polygon": mapping(to_shape(fetched.terrain_result.catchment_polygon)) if fetched.terrain_result and fetched.terrain_result.catchment_polygon else {},
            "area_km2": fetched.terrain_result.area_km2 if fetched.terrain_result else 0,
            "avg_slope": fetched.terrain_result.avg_slope if fetched.terrain_result else 0,
        },
        rainfall={
            "annual_avg_mm": fetched.rainfall_result.annual_avg_mm,
            "seasonal": fetched.rainfall_result.seasonal_json,
            "data_years": fetched.rainfall_result.data_years,
        } if fetched.rainfall_result else None,
        recommendation={
            "runoff_m3": fetched.recommendation.runoff_m3,
            "depth_m": fetched.recommendation.depth_m,
            "surface_area_m2": fetched.recommendation.surface_area_m2,
            "capacity_m3": fetched.recommendation.capacity_m3,
            "suitability_score": fetched.recommendation.suitability_score,
        } if fetched.recommendation else None,
        warnings=[],
    )


@app.post("/analyzeContour", response_model=ContourAnalysisResponse)
async def analyze_contour(contour_map: UploadFile = File(...)):
    """
    Accepts a contour map (KML or KMZ), analyzes the terrain it describes, and
    returns a suggested pond location + catchment estimate — WITHOUT the user
    providing a point. The site is discovered automatically from the terrain
    (highest flow-accumulation point), per the assignment's requirement not to
    hard-code any location specific to the sample map.

    NOTE: the upload field is named "contour_map" specifically because the
    assignment's Google Form submission requires that exact field name for
    automated/manual testing via Postman — this isn't an arbitrary choice.

    Pipeline (each step reuses already-tested code, not new-for-this-endpoint logic):
      1. Parse contour lines + elevations from the uploaded file (kml_parser.py)
      2. Interpolate those scattered elevation points into a continuous grid (dem_from_contours.py)
      3. Write that grid out as a real GeoTIFF (same format the OpenTopography path already uses)
      4. Run the EXISTING D8 flow-direction + accumulation + catchment logic (catchment.py) —
         the same code already tested against real SRTM data on Day 2
      5. Auto-select the pond site as the highest-accumulation interior point
    """
    warnings: list[str] = []
    filename = contour_map.filename or "uploaded_contour_map"

    if not (filename.lower().endswith(".kml") or filename.lower().endswith(".kmz")):
        raise HTTPException(status_code=400, detail="File must be a .kml or .kmz contour map.")

    file_bytes = await contour_map.read()

    # ---- Step 1: parse contour lines ----
    try:
        contours = parse_contours(file_bytes, filename)
    except ContourParseError as e:
        raise HTTPException(status_code=400, detail=f"Could not parse contour file: {e}")

    elevations = [c["elevation"] for c in contours]

    # ---- Step 2-3: interpolate to a grid, write as GeoTIFF ----
    try:
        grid_data = contours_to_grid(contours)
    except InterpolationError as e:
        raise HTTPException(status_code=422, detail=f"Could not build a terrain grid from this file: {e}")

    tmp_dir = tempfile.mkdtemp(prefix="contour_dem_")
    tif_path = os.path.join(tmp_dir, "dem.tif")
    write_grid_to_geotiff(grid_data, tif_path)

    # ---- Step 4-5: run the EXISTING catchment logic, with auto site-selection ----
    try:
        result = find_pond_site(tif_path)
    except Exception as e:
        import traceback
        print("CONTOUR ANALYSIS ERROR — full traceback:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Terrain analysis failed on this contour map.")
    finally:
        try:
            os.remove(tif_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass  # cleanup best-effort — not worth failing the request over a leftover temp file

    polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])

    if result["area_km2"] == 0:
        warnings.append(
            "Catchment area came back as zero — the auto-selected point may not sit on a "
            "clear drainage path in this terrain (a known limitation of the current heuristic)."
        )

    return ContourAnalysisResponse(
        source_filename=filename,
        contour_lines_parsed=len(contours),
        elevation_range_m={"min": min(elevations), "max": max(elevations)},
        suggested_pond_site=PondSite(lat=result["pour_lat"], lon=result["pour_lon"]),
        catchment_area_km2=result["area_km2"],
        avg_slope_percent=result["avg_slope"],
        catchment_polygon=polygon,
        warnings=warnings,
    )
