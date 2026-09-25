# High-Level Design Document
## AI-based Village Pond Planning System

| | |
|---|---|
| **Course** | Computer System Design |
| **Assignment** | Assignment 1 |
| **Document** | High-Level Design (HLD) |
| **Date** | August 10, 2026 |

---

## 1. Introduction

### 1.1 Purpose
This document defines the high-level architecture of a web-based system that recommends suitable village pond locations by analyzing terrain elevation, catchment area, and historical rainfall, and presents the results through an interactive map interface.

### 1.2 Scope
In scope: satellite/contour visualization, catchment delineation, rainfall data retrieval, runoff estimation, pond depth/capacity recommendation, and results overlay for a single admin-selected location per village.

Out of scope: land ownership/legal clearance, real-time hydrological monitoring post-construction, multi-village batch optimization (though the architecture doesn't preclude adding it later).

### 1.3 Design Constraints
- Must rely on **free/public APIs** for elevation and rainfall (no budget for commercial geospatial services).
- External APIs are **rate-limited and occasionally slow** — this shapes several design decisions below (caching, async orchestration, graceful degradation).
- Single-team, ~4-week build — favors a modular monolith over true microservices, while keeping module boundaries clean enough to split later if needed.

---

## 2. System Architecture

### 2.1 Architecture Style
**Modular monolith with a service-oriented internal structure.** The backend is one deployable FastAPI application, but internally partitioned into three independent modules (Terrain, Rainfall, Recommendation) that communicate only through well-defined function/interface boundaries — not shared global state. This is deliberate: true microservices would add network overhead and deployment complexity with no real benefit at this scale, but keeping the modules decoupled means any one of them (e.g., swapping the elevation provider) can change without touching the others, and the module boundaries map cleanly onto whoever on the team owns which piece.

### 2.2 Architecture Diagram

```
                         ┌──────────────────────────┐
                         │        CLIENT (Browser)    │
                         │  Leaflet map · Village      │
                         │  search · Results panel     │
                         └─────────────┬─────────────┘
                                       │ HTTPS / JSON (REST)
                         ┌─────────────▼─────────────┐
                         │   API LAYER (FastAPI)       │
                         │  Validation · Orchestration  │
                         │  Response cache · Auth (opt.) │
                         └───┬───────────┬───────────┘
               ┌─────────────┘           └─────────────┐
               ▼                                        ▼
     ┌───────────────────┐                    ┌───────────────────┐
     │  TERRAIN MODULE     │                    │  RAINFALL MODULE    │
     │  DEM fetch          │                    │  Historical          │
     │  Flow-direction (D8)│                    │  precipitation query  │
     │  Catchment polygon  │                    │  Seasonal aggregation │
     └──────────┬──────────┘                    └──────────┬──────────┘
                │                                          │
                └───────────────────┬──────────────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │   RECOMMENDATION MODULE          │
                    │   Runoff estimation (Rational)    │
                    │   Depth/capacity sizing            │
                    │   Suitability scoring              │
                    └───────────────┬───────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │   DATA LAYER                       │
                    │   PostgreSQL + PostGIS              │
                    │   File/object storage (DEM tiles)   │
                    │   Redis (response cache)            │
                    └───────────────────────────────┘

     External:  OpenTopography/OpenZenith (DEM)  ·  Open-Meteo/NASA POWER (rainfall)  ·  Basemap tiles (satellite imagery)
```

### 2.3 Key Architectural Decisions & Trade-offs

| Decision | Chosen approach | Alternative considered | Why |
|---|---|---|---|
| Service granularity | Modular monolith | True microservices per module | Avoids network hops between tightly-coupled steps of one request; still keeps clean interfaces for future split |
| Terrain ↔ Rainfall calls | **Parallel (async)** | Sequential | The two calls are independent — running them concurrently with `asyncio.gather` roughly halves the external-API wait time, which matters since these APIs are the slowest part of the request |
| Caching layer | Redis, keyed by rounded `(lat, lon)` grid cell | No caching / re-fetch every time | External APIs are rate-limited; caching also makes repeat demos in front of the professor fast and reliable |
| Catchment computation | Server-side, precomputed on request | Client-side (in-browser) | Flow-accumulation over a DEM is compute-heavy and needs raster libraries (rasterio/numpy) not practical in-browser |
| Runoff formula | Rational Method (`Q = C·I·A`) | SCS Curve Number method | CN needs soil-type + land-use classification data that's hard to source reliably for arbitrary villages in the project timeframe; Rational Method needs only catchment area, rainfall intensity, and a land-cover-based runoff coefficient — defensible and implementable |
| Database | PostgreSQL + PostGIS | MongoDB (from suggested stack) | Catchment polygons and spatial containment queries ("is this point inside an existing water body") are naturally relational + geometric; PostGIS gives this for free where MongoDB would need manual geo-indexing logic |

---

## 3. Component Design

### 3.1 Client Layer
- **Map component**: Leaflet.js, layered — base satellite tile layer, contour overlay layer, catchment polygon layer, pond marker layer.
- **Search/selection**: village name search (geocoding) or direct map click; emits `{lat, lon}` to the API layer.
- **Results panel**: renders catchment area, annual rainfall, runoff volume, recommended depth/capacity, and suitability score returned by the backend.

### 3.2 API Layer
Single FastAPI application exposing REST endpoints (see §5). Responsibilities:
1. Validate incoming coordinates (bounds check, reject nonsensical lat/lon).
2. Check Redis cache for this grid cell; return cached result if present and not stale (TTL — rainfall data doesn't need to refresh often, so a multi-day TTL is reasonable).
3. On cache miss, call Terrain and Rainfall modules **concurrently**.
4. Pass both results into the Recommendation module.
5. Persist the result to PostgreSQL and cache it.
6. Return the consolidated JSON to the client.

### 3.3 Terrain Module
- Fetches DEM raster for the village bounding box (OpenTopography SRTM 30m or OpenZenith).
- Computes flow direction (D8 algorithm) and flow accumulation to delineate the catchment draining into the candidate point.
- Applies a slope filter (e.g., <5–8% gradient) to flag land plausibly excavable for a pond.
- **Interface**: `get_catchment(lat, lon, radius_km) -> {catchment_polygon: GeoJSON, area_km2: float, avg_slope: float}`

### 3.4 Rainfall Module
- Queries Open-Meteo (or NASA POWER) historical daily precipitation for the coordinates, typically 10+ years of data.
- Aggregates to annual mean and seasonal (monsoon vs. non-monsoon) breakdown.
- **Interface**: `get_rainfall_stats(lat, lon) -> {annual_avg_mm: float, seasonal: dict, data_years: int}`

### 3.5 Recommendation Module
- **Runoff estimation** via the Rational Method: `Q = C × I × A`, where `C` is a runoff coefficient (looked up from a small land-cover table, e.g. 0.3–0.5 for rural/agricultural terrain), `I` is design rainfall intensity derived from the rainfall module's data, and `A` is catchment area from the terrain module.
- **Pond sizing**: solves for depth/area such that `Volume ≈ target_fraction × Q_seasonal`, constrained to realistic depth bounds (2–4 m).
- **Suitability score**: weighted combination of slope suitability, catchment adequacy, and rainfall reliability (e.g., 0–100 scale) — lets the admin compare multiple candidate points if that stretch goal is implemented.
- **Interface**: `recommend(catchment, rainfall_stats) -> {runoff_m3: float, depth_m: float, surface_area_m2: float, capacity_m3: float, suitability_score: float}`

### 3.6 Data Layer
- **PostgreSQL + PostGIS**: village metadata, cached analysis results, spatial geometry columns for catchment polygons.
- **Redis**: fast key-value cache for repeat queries on the same grid cell.
- **File/object storage**: raw DEM tiles cached locally to avoid re-downloading from the elevation API on every request to the same area.

---

## 4. Data Flow (Sequence)

```
Client                API Layer          Terrain Module   Rainfall Module   Recommendation Module   DB/Cache
  │  select point         │                    │                │                    │                │
  ├──────────────────────►│                    │                │                    │                │
  │                        ├─ check cache ─────────────────────────────────────────────────────────►│
  │                        │◄────────── cache miss ────────────────────────────────────────────────┤
  │                        ├── get_catchment() ►│                │                    │                │
  │                        ├── get_rainfall_stats() ─────────────►│                    │                │
  │                        │◄── catchment result │                │                    │                │
  │                        │◄──────────────── rainfall result ────┤                    │                │
  │                        ├── recommend(catchment, rainfall) ────────────────────────►│                │
  │                        │◄──────────────────────────────── recommendation ──────────┤                │
  │                        ├── persist + cache result ────────────────────────────────────────────────►│
  │◄── consolidated JSON ──┤                    │                │                    │                │
```

Terrain and Rainfall calls are issued concurrently (both only depend on `{lat, lon}`), and the Recommendation module runs only after both complete — this is the one hard sequencing dependency in the whole flow.

---

## 5. API Design (High-Level)

| Endpoint | Method | Request | Response (summary) |
|---|---|---|---|
| `/api/villages/search` | GET | `?q=<name>` | List of matching villages with centroid coordinates |
| `/api/analyze` | POST | `{lat, lon, village_id?}` | `{catchment, rainfall, recommendation}` consolidated result |
| `/api/analyze/{request_id}` | GET | — | Retrieve a previously computed result by ID |
| `/api/villages/{id}/history` | GET | — | Past analysis requests for a village |

FastAPI auto-generates OpenAPI/Swagger docs from these route definitions, which directly satisfies the "API documentation" deliverable without extra work.

---

## 6. Database Schema

| Entity | Fields | Notes |
|---|---|---|
| `village` | `id (PK)`, `name`, `centroid (geometry)`, `boundary (geometry, nullable)` | |
| `analysis_request` | `id (PK)`, `village_id (FK)`, `point (geometry)`, `created_at` | One row per user query |
| `terrain_result` | `request_id (FK)`, `catchment_polygon (geometry)`, `area_km2`, `avg_slope` | |
| `rainfall_result` | `request_id (FK)`, `annual_avg_mm`, `seasonal_json` | |
| `pond_recommendation` | `request_id (FK)`, `runoff_m3`, `depth_m`, `surface_area_m2`, `capacity_m3`, `suitability_score` | |

All geometry columns use PostGIS `GEOMETRY(Point/Polygon, 4326)` for standard WGS84 lat/lon.

---

## 7. Non-Functional Requirements

### 7.1 Performance / Capacity (rough estimates for a course-scale deployment)
- Expected load: single-digit concurrent users (professor + team during demo), not production traffic — so no load-balancing needed, but the design shouldn't preclude it.
- DEM tile size: SRTM 30m tiles are typically a few MB per village bounding box — cached locally after first fetch.
- Target response time: **first request** to a new area — a few seconds (bounded mostly by external API latency); **cached request** — under 200ms.
- Cache TTL: rainfall data cached for days (doesn't change), terrain data cached indefinitely per tile (elevation is static).

### 7.2 Reliability & Failure Handling
- If the elevation API times out or errors: return a clear error state to the client rather than a partial/incorrect catchment — don't silently substitute default values, since terrain analysis is worth the most marks and a silently wrong catchment is worse than an explicit failure.
- If the rainfall API fails but terrain succeeds: degrade gracefully — show catchment/terrain results with a "rainfall data unavailable" flag rather than blocking the whole response.
- All external API calls wrapped with timeouts and retries (e.g., 2 retries with backoff) before surfacing a failure to the user.

### 7.3 Security
- External API keys stored server-side (environment variables), never exposed to the frontend.
- Input validation on all coordinates to prevent abuse of rate-limited external quotas.

---

## 8. Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Leaflet.js (mapping) + React or vanilla JS |
| Backend | Python, FastAPI |
| Geospatial processing | `rasterio` + `numpy` for DEM flow-accumulation; OpenCV for auxiliary raster ops |
| Database | PostgreSQL + PostGIS |
| Cache | Redis |
| Elevation API | OpenTopography (SRTM 30m) or OpenZenith |
| Rainfall API | Open-Meteo Historical Weather API or NASA POWER |

---

## 9. Deployment View
Single deployable backend (FastAPI app container) + PostgreSQL instance + Redis instance, all runnable via `docker-compose` for local development and demo purposes. No need for orchestration (Kubernetes etc.) at this scale — noted here explicitly as a conscious scope decision, not an oversight.

---

## 10. Assumptions
- A single admin-selected candidate point is analyzed per request (multi-point ranking is a possible extension, supported by the suitability-score field already in the schema, but not required for the base deliverable).
- Runoff coefficient values are approximated from standard rural/agricultural land-cover tables rather than a full land-use classification pipeline.
- Satellite imagery for requirement 1 is served as a basemap tile layer rather than raw processed satellite scenes, which is sufficient for visualization purposes.
