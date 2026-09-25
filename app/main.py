"""
API LAYER — Coordinator for the AI-based Village Pond Planning System.

Endpoints:
  1. GET  /                         -> Interactive Leaflet Frontend Web Application
  2. POST /api/analyze             -> Point-based Catchment & Pond Analysis
  3. GET  /api/analyze/{id}        -> Retrieve analysis by ID
  4. POST /api/analyze-area        -> Land Area Selection Analysis (bounding box / polygon)
  5. POST /analyzeContour          -> Contour Map (KML/KMZ) Analysis
  6. GET  /api/villages/search     -> Village Geocoding & Search
  7. GET  /api/villages/{id}/history -> Past analyses for a specific village
  8. GET  /api/analyses/recent     -> Recent global analyses
  9. GET  /api/health              -> Health and uptime check

Docs auto-generated at: /docs
"""

import os
import time
import tempfile
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ContourAnalysisResponse,
    PondSite,
    TerrainResult,
    RainfallResult,
    RecommendationResult,
    BoundingBox,
    AnalyzeAreaRequest,
    AreaAnalysisResponse,
    VillageSearchResponse,
    HealthResponse,
)
from app.modules.kml_parser import parse_contours, ContourParseError
from app.modules.dem_from_contours import contours_to_grid, write_grid_to_geotiff, InterpolationError
from app.modules.catchment import find_pond_site, catchment_to_geojson
from app.modules.area_analysis import analyze_land_area
from app.modules.village_search import search_villages

START_TIME = time.time()

app = FastAPI(
    title="AI-based Village Pond Planning System",
    description="Interactive geospatial system for recommending optimal village pond locations using terrain elevation, D8 catchment delineation, and historical precipitation.",
    version="1.0.0",
)

# Mount static files for Leaflet frontend
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def on_startup():
    try:
        from app.db.database import engine, Base
        Base.metadata.create_all(bind=engine)
        print("✓ Connected to PostgreSQL database and initialized tables.")
    except Exception as e:
        print(f"NOTICE: Database not connected at startup ({e}). Operating in memory-resilient mode.")


@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "ok",
        "service": "AI-based Village Pond Planning System",
        "docs": "/docs",
        "endpoints": ["/api/analyze", "/api/analyze-area", "/analyzeContour", "/api/villages/search"],
    }


def _get_db_lazy():
    """Yields a database session if available, otherwise yields None gracefully."""
    try:
        from app.db.database import get_db
        yield from get_db()
    except Exception:
        yield None


# ---------- Point-based Analysis ----------

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, db=Depends(_get_db_lazy)):
    import asyncio
    from app.modules.terrain import get_catchment, TerrainDataError
    from app.modules.rainfall import get_rainfall_stats, RainfallDataError
    from app.modules.recommendation import recommend

    warnings: list[str] = []

    # 1. Check cache if database session is active
    if db is not None:
        try:
            from app.db.cache import get_cached_response
            cached = get_cached_response(db, req.lat, req.lon)
            if cached is not None:
                return AnalyzeResponse(**cached)
        except Exception:
            pass

    # 2. Fire Terrain and Rainfall calls concurrently
    terrain_task = asyncio.create_task(get_catchment(req.lat, req.lon))
    rainfall_task = asyncio.create_task(get_rainfall_stats(req.lat, req.lon))

    # 3. Terrain result
    try:
        terrain_result = await terrain_task
    except TerrainDataError as e:
        rainfall_task.cancel()
        raise HTTPException(status_code=502, detail=f"Terrain data unavailable: {e}")

    # 4. Rainfall result with graceful fallback
    rainfall_result = None
    try:
        rainfall_result = await rainfall_task
    except RainfallDataError as e:
        warnings.append("Rainfall API query failed — using regional climate baseline.")
        rainfall_result = RainfallResult(
            annual_avg_mm=1150.0,
            seasonal={"monsoon_mm": 920.0, "non_monsoon_mm": 230.0},
            data_years=10,
        )

    # 5. Recommendation
    recommendation_result = None
    if rainfall_result is not None:
        recommendation_result = recommend(terrain_result, rainfall_result)

    # 6. Persist to DB if available
    request_id = int(time.time() * 1000) % 1_000_000_000
    if db is not None:
        try:
            from app.db import crud
            db_request = crud.create_analysis_request(db, lat=req.lat, lon=req.lon, village_id=req.village_id)
            request_id = db_request.id
            crud.save_terrain_result(db, request_id, terrain_result)
            if rainfall_result is not None:
                crud.save_rainfall_result(db, request_id, rainfall_result)
            if recommendation_result is not None:
                crud.save_recommendation(db, request_id, recommendation_result)
        except Exception as e:
            print(f"Database write skipped: {e}")

    response = AnalyzeResponse(
        request_id=request_id,
        lat=req.lat,
        lon=req.lon,
        terrain=terrain_result,
        rainfall=rainfall_result,
        recommendation=recommendation_result,
        warnings=warnings,
    )

    if db is not None and not warnings:
        try:
            from app.db.cache import set_cached_response
            set_cached_response(db, req.lat, req.lon, response.model_dump())
        except Exception:
            pass

    return response


@app.get("/api/analyze/{request_id}", response_model=AnalyzeResponse)
async def get_analysis(request_id: int, db=Depends(_get_db_lazy)):
    if db is None:
        raise HTTPException(status_code=503, detail="Database storage is not active.")

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


# ---------- Land Area Selection Analysis ----------

@app.post("/api/analyze-area", response_model=AreaAnalysisResponse)
async def analyze_area_endpoint(req: AnalyzeAreaRequest):
    """
    Analyzes a user-selected land area (bounding box) on the map:
    Discovers optimal natural pond site, delineates catchment,
    and calculates expected water volume that can be collected.
    """
    return await analyze_land_area(req.bounds)


# ---------- Contour Map Upload Analysis ----------

@app.post("/analyzeContour", response_model=ContourAnalysisResponse)
async def analyze_contour(contour_map: UploadFile = File(...)):
    """
    Accepts a contour map (.kml or .kmz), auto-discovers optimal pond site via D8
    flow-accumulation, delineates catchment, calculates runoff volume, and sizes the pond.
    """
    warnings: list[str] = []
    filename = contour_map.filename or "uploaded_contour_map"

    if not (filename.lower().endswith(".kml") or filename.lower().endswith(".kmz")):
        raise HTTPException(status_code=400, detail="File must be a .kml or .kmz contour map.")

    file_bytes = await contour_map.read()

    # Step 1: parse contour lines
    try:
        contours = parse_contours(file_bytes, filename)
    except ContourParseError as e:
        raise HTTPException(status_code=400, detail=f"Could not parse contour file: {e}")

    elevations = [c["elevation"] for c in contours]

    # Step 2-3: interpolate to grid and write as GeoTIFF
    try:
        grid_data = contours_to_grid(contours)
    except InterpolationError as e:
        raise HTTPException(status_code=422, detail=f"Could not build a terrain grid from this file: {e}")

    tmp_dir = tempfile.mkdtemp(prefix="contour_dem_")
    tif_path = os.path.join(tmp_dir, "dem.tif")
    write_grid_to_geotiff(grid_data, tif_path)

    # Step 4-5: run flow analysis and auto-discover site
    try:
        result = find_pond_site(tif_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Terrain analysis failed on this contour map.")
    finally:
        try:
            if os.path.exists(tif_path):
                os.remove(tif_path)
            os.rmdir(tmp_dir)
        except OSError:
            pass

    polygon = catchment_to_geojson(result["grid"], result["catchment_mask"])

    if result["area_km2"] == 0:
        warnings.append(
            "Catchment area came back as zero — the auto-selected point may not sit on a "
            "clear drainage path in this terrain."
        )

    # Step 6: Compute rainfall & recommendation for the auto-discovered pond site
    rainfall_result = None
    try:
        from app.modules.rainfall import get_rainfall_stats
        rainfall_result = await get_rainfall_stats(result["pour_lat"], result["pour_lon"])
    except Exception:
        rainfall_result = RainfallResult(
            annual_avg_mm=1180.0,
            seasonal={"monsoon_mm": 940.0, "non_monsoon_mm": 240.0},
            data_years=10,
        )

    from app.modules.recommendation import recommend
    terrain_res = TerrainResult(
        catchment_polygon=polygon,
        area_km2=result["area_km2"],
        avg_slope=result["avg_slope"],
    )
    rec_result = recommend(terrain_res, rainfall_result)

    return ContourAnalysisResponse(
        source_filename=filename,
        contour_lines_parsed=len(contours),
        elevation_range_m={"min": min(elevations), "max": max(elevations)},
        suggested_pond_site=PondSite(lat=result["pour_lat"], lon=result["pour_lon"]),
        catchment_area_km2=result["area_km2"],
        avg_slope_percent=result["avg_slope"],
        catchment_polygon=polygon,
        expected_water_volume_m3=rec_result.runoff_m3,
        rainfall=rainfall_result,
        recommendation=rec_result,
        warnings=warnings,
    )


# ---------- Village Search & History ----------

@app.get("/api/villages/search", response_model=VillageSearchResponse)
async def search_village_endpoint(q: str = Query("", description="Village or district name")):
    results = await search_villages(q)
    return VillageSearchResponse(query=q, results=results)


@app.get("/api/villages/{village_id}/history")
async def get_village_history_endpoint(village_id: int, db=Depends(_get_db_lazy)):
    if db is None:
        return {"village_id": village_id, "history": []}
    from app.db import crud
    from geoalchemy2.shape import to_shape
    rows = crud.get_village_history(db, village_id)
    history = []
    for r in rows:
        pt = to_shape(r.point)
        history.append({
            "request_id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "lat": pt.y,
            "lon": pt.x,
            "area_km2": r.terrain_result.area_km2 if r.terrain_result else None,
            "runoff_m3": r.recommendation.runoff_m3 if r.recommendation else None,
            "suitability_score": r.recommendation.suitability_score if r.recommendation else None,
        })
    return {"village_id": village_id, "history": history}


@app.get("/api/analyses/recent")
async def get_recent_analyses_endpoint(db=Depends(_get_db_lazy)):
    if db is None:
        return {"analyses": []}
    from app.db import crud
    from geoalchemy2.shape import to_shape
    rows = crud.get_recent_analyses(db, limit=12)
    analyses = []
    for r in rows:
        pt = to_shape(r.point)
        analyses.append({
            "request_id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "lat": round(pt.y, 5),
            "lon": round(pt.x, 5),
            "area_km2": r.terrain_result.area_km2 if r.terrain_result else 0,
            "runoff_m3": r.recommendation.runoff_m3 if r.recommendation else 0,
            "suitability_score": r.recommendation.suitability_score if r.recommendation else 0,
        })
    return {"analyses": analyses}


# ---------- System Health & Monitoring ----------

@app.get("/api/health", response_model=HealthResponse)
async def health_check(db=Depends(_get_db_lazy)):
    import resource
    db_status = "connected" if db is not None else "standby"
    mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mem_mb = mem_kb / 1024.0 if mem_kb > 10000 else mem_kb  # linux returns KB
    return HealthResponse(
        status="healthy",
        service="AI-based Village Pond Planning System",
        database=db_status,
        uptime_seconds=round(time.time() - START_TIME, 1),
        memory_mb=round(mem_mb, 1),
        pid=os.getpid(),
    )
