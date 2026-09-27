# Bhagiratha (भगीरथ)
## AI-Based Village Pond Planning & Catchment Delineation System

> *Named after the legendary sage-king Bhagiratha who brought celestial waters down from the heavens to revitalize parched lands, this system automates hydrological analysis and scientific pond planning for rural water conservation.*

---

## Overview

**Bhagiratha** is an end-to-end web-based geospatial decision-support system built for village administrators, irrigation engineers, and rural planners. It automates:
1. **D8 Hydrological Catchment Delineation**: Computes flow directions, depression conditioning, and upstream drainage basins.
2. **Automated Pond Site Selection**: Discovers the optimal natural convergence point via interior peak flow-accumulation scanning without requiring manual coordinates.
3. **Interactive Land Area Selection**: Evaluates any candidate village or agricultural boundary drawn directly on the map.
4. **Precipitation & Runoff Modeling**: Integrates 10-year daily historical weather from Open-Meteo to calculate seasonal runoff via the **Rational Method** ($Q = C \times I \times A$).
5. **Hydraulic Pond Sizing**: Determines optimal pond depth ($2.5$--$4.5\,\text{m}$), required surface footprint, and target storage capacity ($70\%$ seasonal capture).
6. **Rich Interactive Leaflet GIS Map**: Renders satellite basemaps, glowing cyan catchment boundaries, pulsing pond markers, and Chart.js monsoon precipitation graphs.

---

## System Architecture

```
                         ┌──────────────────────────────────────────┐
                         │             CLIENT (Browser)             │
                         │   Leaflet Satellite Map · Area Drawing   │
                         │   Village Search · Analytics Dashboard   │
                         └────────────────────┬─────────────────────┘
                                              │ HTTPS / JSON (REST)
                         ┌────────────────────▼─────────────────────┐
                         │          API COORDINATOR (FastAPI)       │
                         │    Validation · Orchestration · Cache    │
                         └───────────┬───────────────────┬──────────┘
                                     │                   │
                  ┌──────────────────▼──┐             ┌──▼──────────────────┐
                  │   TERRAIN ENGINE    │             │ PRECIPITATION ENGINE│
                  │   KML/KMZ Parser    │             │ Open-Meteo 10-Yr DB │
                  │   2D Interpolator   │             │ Seasonal Breakdown  │
                  │   D8 Flow Routing   │             └──────────┬──────────┘
                  │   Auto Pour-Point   │                        │
                  └──────────┬──────────┘                        │
                             │                                   │
                             └─────────────────┬─────────────────┘
                                               ▼
                               ┌───────────────────────────────┐
                               │     RECOMMENDATION ENGINE     │
                               │  Rational Method: Q = C·I·A   │
                               │  Depth & Capacity Sizing      │
                               │  Suitability Scoring (0-100)  │
                               └───────────────┬───────────────┘
                                               ▼
                               ┌───────────────────────────────┐
                               │       PERSISTENCE LAYER       │
                               │  PostgreSQL + PostGIS / Cache │
                               │  In-Memory Resilient Fallback │
                               └───────────────────────────────┘
```

---

## API Endpoints Reference

| Method | Endpoint | Request Payload | Response Summary |
|---|---|---|---|
| `GET` | `/` | — | Interactive Leaflet GIS Web Application |
| `POST` | `/api/analyze` | `{"lat": float, "lon": float, "village_id": int?}` | Catchment polygon, area, slope, rainfall stats, runoff volume, pond sizing |
| `GET` | `/api/analyze/{id}` | Path parameter: `id` | Previously computed analysis retrieved by ID |
| `POST` | `/api/analyze-area` | `{"bounds": {"min_lat", "max_lat", "min_lon", "max_lon"}}` | Discovers optimal pond site within drawn area, basin boundary, volume, and sizing |
| `POST` | `/analyzeContour` | Multipart form: `contour_map` (.kml / .kmz) | Auto-discovered site, 1,355 lines parsed, 3.9116 km² basin, 1.71M m³ runoff, pond dimensions |
| `GET` | `/api/villages/search` | Query: `?q=<name>` | Matching Indian villages/districts with centroid coordinates |
| `GET` | `/api/villages/{id}/history` | Path parameter: `id` | Past analysis runs for the specified village |
| `GET` | `/api/analyses/recent` | — | Recent 12 analysis runs across all sessions |
| `GET` | `/api/health` | — | Health check: uptime, memory RSS, PID, and database status |

---

## Database Architecture: Localhost vs. Remote SSH

- **Local Machine**: PostgreSQL + PostGIS runs on `localhost:5433` (Database: `ponddb`, User: `pondapp`).
- **Remote Container (`10.1.75.53:3247`)**:
  - The application includes an **automatic in-memory resilient fallback** (`_IN_MEMORY_CACHE` & `_IN_MEMORY_ANALYSES`). If PostgreSQL is not running locally in the container, the backend operates in zero-dependency resilient mode—all endpoints, history, and caching function smoothly without throwing database errors.
  - To forward your local PostgreSQL to the remote container:
    ```bash
    ssh -R 5433:localhost:5433 -p 2247 student@10.1.75.53
    ```

---

## Local Setup & Quick Start

```bash
# 1. Activate Python 3.12 virtual environment
source .venv/bin/activate

# 2. Configure .env
cp .env.example .env
# Edit OPENTOPOGRAPHY_API_KEY and DATABASE_URL if needed

# 3. Launch Development Server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Open Application in Browser
http://127.0.0.1:8000/
# Interactive API documentation at: http://127.0.0.1:8000/docs
```

---

## Automated Verification & Test Suite

```bash
# Run the full suite (27 tests):
.venv/bin/pytest tests/ -q

# Individual groups:
.venv/bin/pytest tests/test_contour.py      # Real benchmark 1m contour map (1355 lines)
.venv/bin/pytest tests/test_extended.py     # KMZ archive, empty files, malformed XML, area selection, health
.venv/bin/pytest tests/test_scientific.py   # Units, depth bounds, scoring, SRTM int16, parcel containment, rainfall fallback
.venv/bin/pytest tests/test_rainfall.py     # Open-Meteo aggregation & monsoon breakdown
.venv/bin/pytest tests/test_cache.py        # Coarse-grid rounded spatial caching (TTL)
.venv/bin/pytest tests/test_terrain.py      # D8 flow routing & depression filling
.venv/bin/pytest tests/test_db.py           # PostgreSQL+PostGIS spatial geometry persistence
```

Note: several tests query Open-Meteo live, and its free tier limits 10-year queries per day. Avoid re-running the suite many times just before a demo; if the quota runs out, the app uses the bundled data in `data/rainfall_cache.json`.

## Scope of the Recommendation

"Best site" means the point of **maximum runoff convergence**. The system does **not** check existing rivers, canals or tanks, land ownership, land use, soil, groundwater, flood safety, downstream rights, approvals, access or cost. On the sample map the selected point lies in the Shivnath river channel. Treat results as screening recommendations to be verified in the field (see `report/final_report.pdf` §9.2).

---

## Deliverables

- **Live Deployed Web App**: `http://10.1.75.53:3247/`
- **GitHub Repository**: `https://github.com/RahulSeera/pond-planning-backend`
- **Final Report (Overleaf Template)**: `report/final_report.tex`
- **YouTube 5-Minute Demo Script**: `report/YOUTUBE_DEMO_SCRIPT.md`
