# Pond Planning System — Backend

## Two phases in this repo

### Phase 1 — point-based analysis (`POST /api/analyze`)
User provides `{lat, lon}` → real OpenTopography DEM + Open-Meteo rainfall →
Rational Method runoff + pond sizing → saved to PostgreSQL+PostGIS, cached.

### Phase 2 — contour-map analysis (`POST /analyzeContour`)
User uploads a KML/KMZ contour map → terrain is parsed and interpolated into a
DEM → the SAME D8 flow-direction/catchment code from Phase 1 runs on it →
a pond site is picked **automatically** (highest flow-accumulation point,
not user-provided) → catchment area/slope/polygon returned as JSON.

This is the important design point if asked: Phase 2 does NOT duplicate the
terrain analysis logic. `catchment.py`'s D8/flow-accumulation code doesn't
know or care whether its DEM came from a downloaded SRTM tile or from
interpolated contour lines — it just operates on a GeoTIFF either way. Only
the *input* pipeline (parse KML → interpolate → write GeoTIFF) is new.

## Status

| Module | Status |
|---|---|
| API layer (`main.py`) | Real, tested — both `/api/analyze` and `/analyzeContour` |
| Recommendation (Rational Method) | Real, tested |
| Terrain — D8/catchment (`catchment.py`) | Real, tested — proven against real SRTM data AND real contour-derived data |
| Terrain — OpenTopography fetch | Real, network-tested on the dev machine |
| Rainfall (Open-Meteo) | Real, tested |
| Database (PostgreSQL+PostGIS) | Real, tested on the dev machine |
| Caching | Real, tested |
| **KML/KMZ parser** (`kml_parser.py`) | **Real, tested against the real sample file** — 1355 contour lines, elevation 267-298m |
| **Contour-to-DEM interpolation** (`dem_from_contours.py`) | **Real, tested** — scipy griddata, no gaps in output |
| **Auto pond-site selection** (`find_pond_site` in `catchment.py`) | **Real, tested** — finds a 3.8 km² catchment automatically on the real sample map |

## Setup

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
# fill in OPENTOPOGRAPHY_API_KEY and DATABASE_URL
uvicorn app.main:app --reload
```
Docs (including the contour endpoint) at **http://127.0.0.1:8000/docs**.

## Testing the contour endpoint manually
```bash
curl -X POST http://127.0.0.1:8000/analyzeContour \
  -F "file=@tests/sample_data/contours_1m.kml"
```

## How the catchment estimation approach works (for the report)
1. **Parse**: every `<Placemark>` with a `<LineString>` is a contour line; its elevation
   comes from the `<name>` tag (this sample file's convention) or, as a fallback for
   other KML exports, the average Z-coordinate of its points.
2. **Interpolate**: every point along every contour line is a known (lon, lat, elevation)
   sample. `scipy.interpolate.griddata` builds a continuous elevation grid from these
   scattered points (linear interpolation, nearest-neighbor fallback at the edges).
3. **Flow analysis**: the grid is written as a GeoTIFF and run through the same D8
   flow-direction + flow-accumulation algorithm used for real DEM data.
4. **Site selection**: the interior pixel with the highest flow accumulation is picked
   as the suggested pond site — the point where the most water naturally converges.
   Border pixels are excluded (accumulation is artificially inflated at a DEM's edge).
5. **Catchment stats**: area and average slope are computed the same way as Phase 1,
   with the same degree-to-meters unit correction.

## Generalization (per the assignment's requirement)
Nothing in the pipeline is hardcoded to this sample map:
- The parser walks the KML tree structurally (any Placemark with a LineString),
  not by folder name or position.
- Elevation extraction falls back to Z-coordinates if `<name>` isn't numeric,
  covering KML exports that encode elevation differently.
- The interpolation grid is sized from the actual bounding box of whatever
  points are parsed.
- The pond site is discovered from the terrain's own flow pattern, not read
  from a lookup table.

## Known limitations (honest, not hidden)
- If the auto-selected site doesn't land on a clear drainage line, the catchment
  area can come back very small — the API surfaces this as a warning rather than
  silently returning a misleading tiny number.
- Elevation-to-meters pixel conversion is a latitude-based approximation (same
  simplification as Phase 1), not a full UTM reprojection.
- Contour parsing assumes 2D coordinates or a consistent elevation-per-line
  encoding; a KML mixing both conventions in one file isn't handled.

## Tests (all passing)
```bash
python3 tests/test_contour.py    # full contour pipeline, real sample file, real HTTP endpoint
python3 tests/test_terrain.py
python3 tests/test_rainfall.py
python3 tests/test_db.py
python3 tests/test_cache.py
```

## What's left for the report deliverables
- GitHub repo — push this project and link it
- API documentation — auto-generated at `/docs`, screenshot or link it
- Demonstration — `tests/test_contour.py`'s output IS your demonstration proof;
  can also screenshot a Swagger UI run against `tests/sample_data/contours_1m.kml`
