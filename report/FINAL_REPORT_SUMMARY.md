# Bhagiratha (भगीरथ): Final Report Summary

**AI-based Village Pond Planning System** · Computer System Design (CSD), IIT Bhilai · Rahul Seera
Full paper: [`report/final_report.tex`](final_report.tex) (ACM `acmart`, compiles cleanly with `latexmk -pdf`)
Live app: <http://10.1.75.53:3247/> (campus network) · Code: <https://github.com/RahulSeera/pond-planning-backend>

---

## 1. What it does

Village ponds are often dug where land is available rather than where water collects, so they stay dry or breach. Given a **clicked point**, a **drawn land parcel**, or an **uploaded KML/KMZ contour map**, Bhagiratha returns:

1. a recommended pond location (the natural drainage convergence point),
2. the upstream catchment boundary (GeoJSON),
3. 10-year historical rainfall (annual and monsoon),
4. expected monsoon runoff volume,
5. pond depth, surface area and capacity, and
6. a 0–100 suitability score,

all overlaid on Esri satellite imagery in a Leaflet map.

## 2. Architecture

Asynchronous **FastAPI modular monolith** with four layers: Leaflet/Chart.js client → API coordination → terrain + precipitation engines → recommendation engine → PostGIS / file-based persistence.

- Terrain and rainfall run concurrently (`asyncio.create_task`). CPU-heavy steps run in worker threads (`asyncio.to_thread`), so `/api/health` stays responsive (≈2 ms during a 13.5 s analysis).
- PostgreSQL is **never** a hard dependency: a 3 s connection test at startup selects PostGIS mode or **persistent-file mode** (`data/analyses_history.json`).

## 3. Algorithms

| Stage | Method |
|---|---|
| Contour ingestion | KML/KMZ parse; elevation from `<name>` (number or regex) or mean *z*; strided decimation ⌊N/20,000⌋ (159,113 → 22,731 points) |
| DEM from contours | SciPy `griddata` linear (Delaunay) + nearest-neighbour hull fill; GeoTIFF with pixel centres on sample points |
| Conditioning | PySheds Priority-Flood depression fill (Barnes et al. 2014) + flat resolution |
| Flow routing | **D8 on a metric grid**: Δx = Δλ·111,320·cos φ, Δy = Δφ·111,320 |
| Pond site | argmax flow accumulation over the interior (8 % border excluded); in parcel mode restricted to the parcel; in point mode snapped to the max-accumulation cell within 2 cells |
| Catchment | Upstream D8 trace → mask → GeoJSON polygon; area from metric cell size; warns (and in point mode re-fetches a larger tile) if the catchment touches the DEM edge |
| Runoff | Q = C·I·A, C = 0.35, I = mean Jun–Sep rainfall depth (m) over 10 years, A in m² → seasonal volume in m³ |
| Sizing | V = 0.70·Q; depth 2.5 m (V ≤ 5,000 m³) → linear → 4.5 m (V ≥ 200,000 m³); area = V/d |
| Suitability | clip₍₅,₉₈₎(0.40·catchment + 0.35·slope + 0.25·rainfall); catchment 100 on 0.5–5 km², slope 100 at ≤ 4 % (−12/pt above), rainfall 100 at ≥ 1000 mm |

## 4. API (9 routes)

| Route | Input | Errors |
|---|---|---|
| `GET /` | — | — |
| `POST /api/analyze` | `{lat, lon, village_id?}` | 422, 502 (DEM unavailable) |
| `GET /api/analyze/{id}` | path id | 404 |
| `POST /api/analyze-area` | `{bounds:{min_lat,max_lat,min_lon,max_lon}, name?}` | 422 (incl. min ≥ max) |
| `POST /analyzeContour` | multipart `contour_map` (.kml/.kmz) | 400 type/empty/parse, 422 grid, 500 flow |
| `GET /api/villages/search?q=` | query string | — (37 curated villages + Nominatim) |
| `GET /api/villages/{id}/history` | path id | — |
| `GET /api/analyses/recent` | — | — (12 newest) |
| `GET /api/health` | — | — (status, db mode, uptime, current RSS MB, pid) |

Degraded results always carry a `warnings[]` entry (bundled or baseline rainfall, synthetic terrain, truncated catchment, flow failure).

## 5. Data model

PostGIS (SRID 4326): `village`, `analysis_request` (POINT), `terrain_result` (catchment GEOMETRY, area, slope), `rainfall_result` (annual, seasonal JSON, years), `pond_recommendation` (runoff, depth, area, capacity, score), `query_cache` (rounded "lat,lon" key, JSON, 7-day TTL).
File mode: `data/analyses_history.json` (≤ 100 records, full sizing figures) + in-memory cache (≤ 500 entries).

## 6. External services

- **OpenTopography** SRTMGL1 (30 m) GeoTIFF, API key in `.env`, 20 s timeout.
- **Open-Meteo** archive, `daily=precipitation_sum`, last 10 full years, 15 s timeout; if unreachable, bundled real archive data (`data/rainfall_cache.json`, 19 points around Durg–Bhilai, nearest within 11 km), else baseline 1150 mm/yr, 920 mm monsoon; always with a note. A background probe and circuit breaker keep requests from waiting on a blocked service.
- **Nominatim**, only when curated matches are fewer than 8; 3 s timeout; failures ignored.

## 7. CSD themes (report Table 2; functional component mapping is Table 1)

| Theme | In Bhagiratha |
|---|---|
| Concurrency | `create_task` hides the 1.2 s rainfall query behind the 12 s DEM download; `to_thread` keeps the event loop free |
| Caching | Rounded 3-decimal (≈110 m) key, 7-day TTL: 13 s → 8 ms on a repeat query |
| Resilience | DB → file mode; rainfall → bundled archive → baseline; DEM → synthetic terrain (flagged); watchdog restarts on failed health check |
| Memory | Decimation bounds Delaunay input below 40k points; lazy DB imports; temp-raster pruning; bounded cache and history |

## 8. Results on `contours_1m.kml` (27 Sep 2026)

| Quantity | Value |
|---|---|
| Input | 1,355 contours, 267–298 m, ≈ 3.2 × 2.6 km |
| Pond site | **21.24171° N, 81.28692° E** |
| Catchment | **3.9116 km²**, slope 3.99 %, valid polygon, not truncated |
| Rainfall (live, 2016–2025) | 1,415.2 mm/yr, 1,251.4 mm monsoon |
| Runoff | **1,713,242 m³** (same on the campus server via bundled archive data) |
| Pond | 4.5 m deep, 266,504 m², capacity 1,199,269 m³ |
| Suitability | 98 / 100 |
| Latency | parse 0.33 s · interpolate 0.72 s · flow 0.15 s · Open-Meteo 1.25 s · end-to-end 2.6–3.7 s |

## 9. Pre-submission audit: what changed

| # | Issue found | Fix |
|---|---|---|
| 1 | D8 used degree spacing (≈7 % E–W bias at 21° N) | D8 runs on a metric grid |
| 2 | GeoTIFF pixel corners (not centres) on sample points; site reported at a cell corner | Centre-aligned transform; site = cell centre |
| 3 | **Real SRTM (int16) tiles crashed Priority-Flood**: area mode silently returned a "45 % of parcel" guess; point mode returned 502 | Normalise to float32 |
| 4 | Area mode could place the pond outside the drawn parcel | Search restricted to the parcel |
| 5 | Clicks one cell off-channel gave tiny catchments; catchments cut off at tile edges went unreported | Pour-point snapping (2 cells); edge detection + larger-tile retry + warning |
| 6 | Catchment score not flat on 0.5–5 km², jump at 0.1 km² | Continuous piecewise-linear score |
| 7 | Contour endpoint silently used a different rainfall baseline | One shared baseline, always warned |
| 8 | DB dependency turned HTTP 502 into a 500 crash when PostgreSQL was up | Let endpoint exceptions propagate |
| 9 | Shared `/tmp/dem_tile.tif` raced between concurrent requests | Per-request temp files |
| 10 | "Load Sample Demo" ran an area query, not the contour file it announced | Now uploads the real `contours_1m.kml` |
| 11 | `GET /api/analyze/{id}` in file mode invented depth 4.5 m, slope 4 % | Stores and returns real figures |
| 12 | `/api/health` reported peak, not current, memory | Reads VmRSS |
| 13 | Container runs on a 1-CPU cgroup but sees 120 cores → thread thrashing (contour 28–49 s) | Thread pools pinned to 1 in `start_server.sh` → 0.7–0.8 s |
| 14 | Blocked Open-Meteo stalled each request up to 45 s | 12 s deadline + 10-min circuit breaker |
| 15 | Watchdog killed the server while it was still starting (~20 s imports) | 90 s startup grace period |
| 16 | Live server ran an older revision (placeholder scoring) | Verified code deployed (backup kept on the server) |
| 17 | Server showed different (baseline) rainfall than the laptop | Bundled real Open-Meteo data for the demo region; server now matches the laptop exactly |
| 18 | First request after a restart took ≈13 s (waiting on the blocked rainfall service) | Background reachability probe + startup warm-up → ≈0.9 s |

Before → after on the reference file: site moved one cell (≈16 m); area 3.8715 → 3.9116 km² (+1.0 %). The old 1,273,723 m³ figure came from a 940 mm fallback rather than measured rainfall.
Tests: **27 passed** (18 original + 9 new in `tests/test_scientific.py`).

## 10. Deployment (container `stu72_sys3`)

Ubuntu 24.04, Python 3.12.3, port 3000 → 3247; `start_server.sh` + a 60 s `watchdog.sh` loop (health probe, restart, temp pruning, log rotation). Observed on 27 Sep 2026: disk **99 % full (3.8 GB free)**, **1-CPU cgroup quota**, no PostgreSQL (file mode), **Open-Meteo and Nominatim blocked**, OpenTopography reachable. After the fixes, the container measured: contour analysis **0.7–0.9 s** (including the first request after a restart) and point analysis **12.6 s**.

## 11. What the system decides, and what it doesn't

- **Point mode** *scores* a location you choose (snapped ≤ 60 m to the drainage line). **Area mode** *picks* the best point inside your parcel. **Contour mode** *picks* the best point on the whole map.
- "Best" means **maximum runoff convergence**, nothing more. On the reference map that point is **in the Shivnath river channel**: hydrologically right, but a check-dam location, not a dug pond.
- **Not checked:** existing rivers, canals and tanks; land ownership or encroachment; land use and structures; soil permeability and geology; groundwater and water quality; flood and dam safety; downstream rights and approvals; access, cost and community need.
- The output is a **screening recommendation**; field verification and approvals from the revenue and irrigation authorities are required. Report §9.2.
- **Future work:** OpenStreetMap water-body exclusion (the river and 4 canals are already mapped there), top-k multi-site ranking, land-use and soil layers, cadastral parcels, water balance.

## 12. Limitations

Large catchments imply very large ponds (26.7 ha here), so the result is best read as harvesting potential to split across structures. C is constant; SRTM 30 m misses fine channels that the 1 m contours capture; there's a single outlet with no multi-site ranking; and there's no evaporation or seepage balance.
