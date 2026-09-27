"""
API LAYER — Coordinator for Bhagiratha: AI-based Village Pond Planning System.
Named after the legendary sage-king Bhagiratha who brought celestial waters to earth.

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

import asyncio
import os
import time
import json
import tempfile
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, List, Dict, Any

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
DB_IS_AVAILABLE = False
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "analyses_history.json")

# In-memory storage buffers for zero-dependency / container-standalone execution.
# Populated from data/analyses_history.json at startup and by every analysis.
IN_MEMORY_ANALYSES: List[Dict[str, Any]] = []
IN_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
MAX_HISTORY_RECORDS = 100
MAX_CACHE_ENTRIES = 500


def _load_history_from_file():
    global IN_MEMORY_ANALYSES
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list) and loaded:
                    IN_MEMORY_ANALYSES = loaded
        except Exception as e:
            print(f"Notice: Could not load history file: {e}")


def _save_history_to_file():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(IN_MEMORY_ANALYSES[:MAX_HISTORY_RECORDS], f, indent=2)
    except Exception as e:
        print(f"Notice: Could not save history file: {e}")


def _record_analysis(request_id: int, village_id, lat: float, lon: float,
                     terrain: TerrainResult, rec: Optional[RecommendationResult]):
    """Adds one analysis to the (bounded) in-memory history and persists it to the JSON file.
    Stores the full sizing result so GET /api/analyze/{id} can return real values later."""
    IN_MEMORY_ANALYSES.insert(0, {
        "request_id": request_id,
        "village_id": village_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "area_km2": terrain.area_km2,
        "avg_slope": terrain.avg_slope,
        "runoff_m3": rec.runoff_m3 if rec else 0,
        "depth_m": rec.depth_m if rec else None,
        "surface_area_m2": rec.surface_area_m2 if rec else None,
        "capacity_m3": rec.capacity_m3 if rec else None,
        "suitability_score": rec.suitability_score if rec else 0,
    })
    del IN_MEMORY_ANALYSES[MAX_HISTORY_RECORDS:]
    _save_history_to_file()


def _new_request_id() -> int:
    return int(time.time() * 1000) % 1_000_000_000


app = FastAPI(
    title="Bhagiratha: AI-based Village Pond Planning System",
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
    global DB_IS_AVAILABLE
    _load_history_from_file()
    try:
        from app.db.database import engine, Base, is_db_available
        if is_db_available():
            Base.metadata.create_all(bind=engine)
            DB_IS_AVAILABLE = True
            print("✓ Connected to PostgreSQL database and initialized PostGIS tables.")
        else:
            DB_IS_AVAILABLE = False
            print("NOTICE: PostgreSQL is not reachable. Operating in resilient persistent-file mode.")
    except Exception as e:
        DB_IS_AVAILABLE = False
        print(f"NOTICE: Database operating in memory-resilient mode ({e}).")

    # Warm up in the background: the first flow-routing call JIT-compiles PySheds'
    # Numba kernels (~14 s on the 1-CPU container). Doing it on a tiny synthetic
    # DEM right after startup makes the first real user request fast.
    import threading
    threading.Thread(target=_warm_up_pipeline, daemon=True).start()

    # Background Open-Meteo reachability probe (feeds the rainfall circuit breaker).
    if os.environ.get("BHAGIRATHA_DISABLE_RAINFALL_PROBE") != "1":
        from app.modules.rainfall import probe_loop
        threading.Thread(target=lambda: asyncio.run(probe_loop()), daemon=True).start()


def _warm_up_pipeline():
    try:
        from app.schemas import BoundingBox
        from app.modules.area_analysis import generate_terrain_for_bounds
        from app.modules.dem_from_contours import contours_to_grid
        t0 = time.time()
        tmp_dir = tempfile.mkdtemp(prefix="warmup_dem_")
        tif = os.path.join(tmp_dir, "warmup.tif")
        generate_terrain_for_bounds(BoundingBox(min_lat=21.0, max_lat=21.01, min_lon=81.0, max_lon=81.01), tif, resolution=40)
        res = find_pond_site(tif)
        catchment_to_geojson(res["grid"], res["catchment_mask"])
        contours_to_grid([{"elevation": float(z), "coordinates": [(81.0 + 0.001 * i, 21.0 + 0.001 * z) for i in range(5)]} for z in range(5)])
        os.remove(tif)
        os.rmdir(tmp_dir)
        print(f"Warm-up complete in {time.time() - t0:.1f}s (terrain kernels compiled).", flush=True)
    except Exception as e:
        print(f"NOTICE: warm-up skipped ({e}).", flush=True)


@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "ok",
        "service": "Bhagiratha: AI-based Village Pond Planning System",
        "docs": "/docs",
        "endpoints": ["/api/analyze", "/api/analyze-area", "/analyzeContour", "/api/villages/search"],
    }


def _get_db_lazy():
    """Yields a database session if live, otherwise yields None gracefully."""
    if not DB_IS_AVAILABLE:
        yield None
        return
    try:
        from app.db.database import SessionLocal
        db = SessionLocal()
    except Exception:
        yield None
        return
    # Only session CREATION is guarded above. Exceptions raised by the endpoint
    # itself (e.g. HTTPException 502) are thrown back in at this yield and must
    # propagate — catching them and yielding again crashes the request with a 500.
    try:
        yield db
    finally:
        db.close()


# ---------- Point-based Analysis ----------

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, db=Depends(_get_db_lazy)):
    from app.modules.terrain import get_catchment, TerrainDataError
    from app.modules.rainfall import get_rainfall_stats, RainfallDataError, fallback_rainfall, BUNDLED_RAINFALL_NOTE_PREFIX
    from app.modules.recommendation import recommend

    warnings: list[str] = []
    cache_key = f"{round(req.lat, 3)},{round(req.lon, 3)}"

    # 1. Check cache (PostgreSQL or In-Memory)
    if db is not None:
        try:
            from app.db.cache import get_cached_response
            cached = get_cached_response(db, req.lat, req.lon)
            if cached is not None:
                return AnalyzeResponse(**cached)
        except Exception:
            pass
    elif cache_key in IN_MEMORY_CACHE:
        return AnalyzeResponse(**IN_MEMORY_CACHE[cache_key])

    # 2. Fire Terrain and Rainfall calls concurrently
    terrain_task = asyncio.create_task(get_catchment(req.lat, req.lon))
    rainfall_task = asyncio.create_task(get_rainfall_stats(req.lat, req.lon))

    # 3. Terrain result
    try:
        terrain_result, terrain_warnings = await terrain_task
        warnings.extend(terrain_warnings)
    except TerrainDataError as e:
        rainfall_task.cancel()
        raise HTTPException(status_code=502, detail=f"Terrain data unavailable: {e}")

    # 4. Rainfall result with graceful fallback
    rainfall_result = None
    try:
        rainfall_result = await rainfall_task
    except RainfallDataError:
        rainfall_result, note = fallback_rainfall(req.lat, req.lon)
        warnings.append(note)

    # 5. Recommendation
    recommendation_result = None
    if rainfall_result is not None:
        recommendation_result = recommend(terrain_result, rainfall_result)

    # 6. Persist to DB or In-Memory buffer
    request_id = _new_request_id()
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

    # Record in in-memory history
    _record_analysis(request_id, req.village_id, req.lat, req.lon, terrain_result, recommendation_result)

    response = AnalyzeResponse(
        request_id=request_id,
        lat=req.lat,
        lon=req.lon,
        terrain=terrain_result,
        rainfall=rainfall_result,
        recommendation=recommendation_result,
        warnings=warnings,
    )

    # Cache only full-quality results. A note that bundled REAL archive rainfall was
    # used is not a degradation (same data as a live query), so it doesn't block caching;
    # baseline rainfall or a truncated catchment does, so those get recomputed later.
    if all(w.startswith(BUNDLED_RAINFALL_NOTE_PREFIX) for w in warnings):
        if db is not None:
            try:
                from app.db.cache import set_cached_response
                set_cached_response(db, req.lat, req.lon, response.model_dump())
            except Exception:
                pass
        if len(IN_MEMORY_CACHE) >= MAX_CACHE_ENTRIES:
            IN_MEMORY_CACHE.pop(next(iter(IN_MEMORY_CACHE)))  # evict oldest (dicts keep insertion order)
        IN_MEMORY_CACHE[cache_key] = response.model_dump()

    return response


@app.get("/api/analyze/{request_id}", response_model=AnalyzeResponse)
async def get_analysis(request_id: int, db=Depends(_get_db_lazy)):
    if db is not None:
        try:
            from app.db import crud
            from geoalchemy2.shape import to_shape
            from shapely.geometry import mapping

            fetched = crud.get_analysis_by_id(db, request_id)
            if fetched is not None:
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
        except Exception:
            pass

    # Fallback to in-memory lookup. The history file stores summary figures only
    # (no polygon / rainfall); older records may also lack the sizing fields, in
    # which case the recommendation is left out rather than invented.
    for a in IN_MEMORY_ANALYSES:
        if a.get("request_id") == request_id:
            rec = None
            if a.get("depth_m") is not None:
                rec = RecommendationResult(
                    runoff_m3=a["runoff_m3"], depth_m=a["depth_m"],
                    surface_area_m2=a["surface_area_m2"], capacity_m3=a["capacity_m3"],
                    suitability_score=a["suitability_score"],
                )
            return AnalyzeResponse(
                request_id=request_id,
                lat=a["lat"],
                lon=a["lon"],
                terrain=TerrainResult(catchment_polygon={"type": "Polygon", "coordinates": []},
                                      area_km2=a["area_km2"], avg_slope=a.get("avg_slope") or 0.0),
                rainfall=None,
                recommendation=rec,
                warnings=["Retrieved from file-based history: catchment polygon and rainfall detail are not stored."],
            )

    raise HTTPException(status_code=404, detail="Analysis request not found.")


# ---------- Land Area Selection Analysis ----------

@app.post("/api/analyze-area", response_model=AreaAnalysisResponse)
async def analyze_area_endpoint(req: AnalyzeAreaRequest):
    """
    Analyzes a user-selected land area (bounding box) on the map:
    Discovers optimal natural pond site, delineates catchment,
    and calculates expected water volume that can be collected.
    """
    if req.bounds.min_lat >= req.bounds.max_lat or req.bounds.min_lon >= req.bounds.max_lon:
        raise HTTPException(status_code=422, detail="Bounds must satisfy min_lat < max_lat and min_lon < max_lon.")
    res = await analyze_land_area(req.bounds)
    _record_analysis(
        _new_request_id(), None, res.suggested_pond_site.lat, res.suggested_pond_site.lon,
        TerrainResult(catchment_polygon={}, area_km2=res.catchment_area_km2, avg_slope=res.avg_slope_percent),
        res.recommendation,
    )
    return res


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

    # Step 1: parse contour lines. Parsing, interpolation and flow routing are
    # CPU-bound, so they run in worker threads — keeps the event loop (and the
    # watchdog's /api/health probe) responsive during a large upload.
    try:
        contours = await asyncio.to_thread(parse_contours, file_bytes, filename)
    except ContourParseError as e:
        raise HTTPException(status_code=400, detail=f"Could not parse contour file: {e}")

    elevations = [c["elevation"] for c in contours]

    # Step 2-3: interpolate to grid and write as GeoTIFF
    try:
        grid_data = await asyncio.to_thread(contours_to_grid, contours)
    except InterpolationError as e:
        raise HTTPException(status_code=422, detail=f"Could not build a terrain grid from this file: {e}")

    tmp_dir = tempfile.mkdtemp(prefix="contour_dem_")
    tif_path = os.path.join(tmp_dir, "dem.tif")
    write_grid_to_geotiff(grid_data, tif_path)

    # Step 4-5: run flow analysis and auto-discover site
    try:
        result = await asyncio.to_thread(find_pond_site, tif_path)
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

    if result.get("touches_edge"):
        warnings.append(
            "The catchment reaches the edge of the uploaded contour map, so the true upstream "
            "area may be larger than reported — treat catchment area and runoff as lower bounds."
        )
    if result["area_km2"] == 0:
        warnings.append(
            "Catchment area came back as zero — the auto-selected point may not sit on a "
            "clear drainage path in this terrain."
        )

    # Step 6: Compute rainfall & recommendation for the auto-discovered pond site
    from app.modules.rainfall import get_rainfall_stats, RainfallDataError, fallback_rainfall
    try:
        rainfall_result = await get_rainfall_stats(result["pour_lat"], result["pour_lon"])
    except RainfallDataError:
        rainfall_result, note = fallback_rainfall(result["pour_lat"], result["pour_lon"])
        warnings.append(note)

    from app.modules.recommendation import recommend
    terrain_res = TerrainResult(
        catchment_polygon=polygon,
        area_km2=result["area_km2"],
        avg_slope=result["avg_slope"],
    )
    rec_result = recommend(terrain_res, rainfall_result)

    _record_analysis(_new_request_id(), None, result["pour_lat"], result["pour_lon"], terrain_res, rec_result)

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


# ---------- Bundled sample data (used by the "Load Sample Demo" button) ----------

SAMPLE_CONTOUR_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "tests", "sample_data", "contours_1m.kml")


@app.get("/api/sample-contour", include_in_schema=False)
async def sample_contour():
    """Serves the bundled real 1 m contour survey so the demo runs the genuine contour pipeline."""
    if not os.path.exists(SAMPLE_CONTOUR_FILE):
        raise HTTPException(status_code=404, detail="Sample contour file not installed on this server.")
    return FileResponse(SAMPLE_CONTOUR_FILE, media_type="application/vnd.google-earth.kml+xml",
                        filename="contours_1m.kml")


# ---------- Village Search & History ----------

@app.get("/api/villages/search", response_model=VillageSearchResponse)
async def search_village_endpoint(q: str = Query("", description="Village or district name")):
    results = await search_villages(q)
    return VillageSearchResponse(query=q, results=results)


@app.get("/api/villages/{village_id}/history")
async def get_village_history_endpoint(village_id: int, db=Depends(_get_db_lazy)):
    if db is not None:
        try:
            from app.db import crud
            from geoalchemy2.shape import to_shape
            rows = crud.get_village_history(db, village_id)
            if rows:
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
        except Exception:
            pass

    # In-memory history matching village_id
    matches = [a for a in IN_MEMORY_ANALYSES if a.get("village_id") == village_id]
    return {"village_id": village_id, "history": matches}


@app.get("/api/analyses/recent")
async def get_recent_analyses_endpoint(db=Depends(_get_db_lazy)):
    if db is not None:
        try:
            from app.db import crud
            from geoalchemy2.shape import to_shape
            rows = crud.get_recent_analyses(db, limit=12)
            if rows:
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
        except Exception:
            pass

    return {"analyses": IN_MEMORY_ANALYSES[:12]}


# ---------- System Health & Monitoring ----------

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    import resource
    db_status = "connected (PostgreSQL + PostGIS)" if DB_IS_AVAILABLE else "standby (resilient persistent-file mode)"
    # Current resident set size from /proc (Linux); falls back to peak RSS elsewhere.
    mem_mb = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    mem_mb = int(line.split()[1]) / 1024.0  # kB -> MB
                    break
    except OSError:
        pass
    if mem_mb is None:
        mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    return HealthResponse(
        status="healthy",
        service="Bhagiratha: AI-based Village Pond Planning System",
        database=db_status,
        uptime_seconds=round(time.time() - START_TIME, 1),
        memory_mb=round(mem_mb, 1),
        pid=os.getpid(),
    )

