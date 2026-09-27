"""
Rainfall Module — queries historical rainfall from Open-Meteo and aggregates it.

The API call itself (fetch_historical_rainfall) is REAL code but UNTESTED from this
sandbox — the network here blocks archive-api.open-meteo.com (403 Host not in allowlist).
No API key is needed for Open-Meteo (unlike OpenTopography), so testing this from your
own machine should be simpler — just needs outbound internet access.

The aggregation logic (aggregate_rainfall) IS tested — see tests/test_rainfall.py,
which feeds it a realistic sample response so the math is verified independent of
network access.
"""

import asyncio
import json
import math
import os
import time
from datetime import date
import httpx

from app.schemas import RainfallResult

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# India's monsoon months (rough convention: June-September). Used to split
# "monsoon" vs "non-monsoon" rainfall for the seasonal breakdown.
MONSOON_MONTHS = {6, 7, 8, 9}

# How many years of history to pull. Open-Meteo's archive goes back decades;
# we don't need that much - enough years to get a stable average.
HISTORY_YEARS = 10


# Fallback used ONLY when the Open-Meteo archive can't be reached (e.g. campus
# network outage). A deliberately conservative figure for the Central India
# monsoon belt — lower than the ~1,400 mm/yr the archive actually reports for the
# Durg/Bhilai test site — so a degraded run under- rather than over-sizes the pond.
# Every code path that uses it must also add a user-visible warning.
CLIMATE_BASELINE = {
    "annual_avg_mm": 1150.0,
    "seasonal": {"monsoon_mm": 920.0, "non_monsoon_mm": 230.0},
    "data_years": 0,  # 0 = not measured; distinguishes the baseline from real archive data
}
BASELINE_WARNING = (
    "Open-Meteo rainfall archive unreachable — using a conservative regional climate "
    "baseline (1150 mm/yr, 920 mm monsoon). Runoff and pond size are approximate."
)


def baseline_rainfall() -> RainfallResult:
    """Regional climate baseline (see CLIMATE_BASELINE) as a RainfallResult."""
    return RainfallResult(
        annual_avg_mm=CLIMATE_BASELINE["annual_avg_mm"],
        seasonal=dict(CLIMATE_BASELINE["seasonal"]),
        data_years=CLIMATE_BASELINE["data_years"],
    )


# Real Open-Meteo 10-year statistics for the demo region, pre-fetched by
# scripts/build_rainfall_cache.py on a machine that can reach Open-Meteo. Used
# when the live query fails (e.g. the campus container, whose firewall blocks
# Open-Meteo) before falling back to the regional baseline.
BUNDLED_RAINFALL_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "rainfall_cache.json"
)
# Nearest bundled point must be within this distance: ~0.1° matches the ~9-11 km
# resolution of the reanalysis grid Open-Meteo's archive is built on.
BUNDLED_MAX_DISTANCE_KM = 11.0
_bundled_cache: dict | None = None
BUNDLED_RAINFALL_NOTE_PREFIX = "Live Open-Meteo query unavailable on this network"


def _load_bundled() -> dict:
    global _bundled_cache
    if _bundled_cache is None:
        try:
            with open(BUNDLED_RAINFALL_FILE, encoding="utf-8") as f:
                _bundled_cache = json.load(f)
        except (OSError, ValueError):
            _bundled_cache = {"points": []}
    return _bundled_cache


def _distance_km(lat1, lon1, lat2, lon2) -> float:
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def bundled_rainfall(lat: float, lon: float):
    """Nearest bundled real-archive point within BUNDLED_MAX_DISTANCE_KM as
    (RainfallResult, distance_km, period), or None if none is close enough."""
    data = _load_bundled()
    best, best_d = None, float("inf")
    for p in data.get("points", []):
        d = _distance_km(lat, lon, p["lat"], p["lon"])
        if d < best_d:
            best, best_d = p, d
    if best is None or best_d > BUNDLED_MAX_DISTANCE_KM:
        return None
    result = RainfallResult(
        annual_avg_mm=best["annual_avg_mm"],
        seasonal={"monsoon_mm": best["monsoon_mm"], "non_monsoon_mm": best["non_monsoon_mm"]},
        data_years=best["data_years"],
    )
    return result, best_d, data.get("period", "")


def fallback_rainfall(lat: float, lon: float) -> tuple[RainfallResult, str]:
    """What to use when the live query fails: bundled real archive data if a point
    is close enough, else the regional baseline — always with a user-facing note."""
    hit = bundled_rainfall(lat, lon)
    if hit is not None:
        result, dist_km, period = hit
        return result, (
            f"{BUNDLED_RAINFALL_NOTE_PREFIX} — using bundled Open-Meteo "
            f"archive data ({period}, {result.data_years} years) for a point {dist_km:.1f} km away."
        )
    return baseline_rainfall(), BASELINE_WARNING


class RainfallDataError(Exception):
    """Raised when the rainfall API call fails."""
    pass


# Hard cap on one live query (a healthy 10-year query takes ~1-2 s). httpx's own
# timeouts apply per connection attempt, and a firewalled host with several
# addresses can otherwise stall for 45 s+ (observed on the campus container).
QUERY_DEADLINE_S = 12.0

# Circuit breaker: after a failure, skip live queries for this long and go straight
# to the baseline, so a network that blocks Open-Meteo costs one timeout, not one
# per request.
FAILURE_COOLDOWN_S = 600.0
_last_failure_at: float | None = None


PROBE_INTERVAL_S = 300.0
PROBE_DEADLINE_S = 10.0


async def probe_open_meteo() -> bool:
    """Tiny (5-day) archive query that keeps the circuit breaker's view of the
    network current, so user requests never spend the QUERY_DEADLINE_S discovering
    that Open-Meteo is blocked. Returns True if Open-Meteo answered."""
    global _last_failure_at
    params = {"latitude": 21.24, "longitude": 81.29, "start_date": "2020-07-01",
              "end_date": "2020-07-05", "daily": "precipitation_sum", "timezone": "auto"}
    try:
        async with httpx.AsyncClient(timeout=PROBE_DEADLINE_S) as client:
            resp = await asyncio.wait_for(client.get(OPEN_METEO_URL, params=params), timeout=PROBE_DEADLINE_S)
            resp.raise_for_status()
        _last_failure_at = None
        return True
    except Exception:
        _last_failure_at = time.monotonic()
        return False


async def probe_loop() -> None:
    """Runs forever in a background thread started by main.py."""
    while True:
        ok = await probe_open_meteo()
        print(f"Open-Meteo reachability probe: {'reachable' if ok else 'unreachable — using bundled/baseline rainfall'}", flush=True)
        await asyncio.sleep(PROBE_INTERVAL_S)


async def get_rainfall_stats(lat: float, lon: float) -> RainfallResult:
    """
    Interface contract (unchanged from the stub - main.py doesn't need to change):
      in  -> lat, lon of the selected point
      out -> RainfallResult with annual average and seasonal breakdown

    Raises: RainfallDataError if the API call fails, times out, or was skipped
            because it failed within the last FAILURE_COOLDOWN_S seconds.
    """
    global _last_failure_at
    if _last_failure_at is not None and time.monotonic() - _last_failure_at < FAILURE_COOLDOWN_S:
        raise RainfallDataError("Skipped live query: Open-Meteo failed recently (circuit breaker open).")
    try:
        raw = await asyncio.wait_for(fetch_historical_rainfall(lat, lon), timeout=QUERY_DEADLINE_S)
        result = aggregate_rainfall(raw)
    except asyncio.TimeoutError:
        _last_failure_at = time.monotonic()
        raise RainfallDataError(f"Rainfall query exceeded {QUERY_DEADLINE_S:.0f} s.")
    except RainfallDataError:
        _last_failure_at = time.monotonic()
        raise
    _last_failure_at = None
    return result


async def fetch_historical_rainfall(lat: float, lon: float) -> dict:
    """
    Calls Open-Meteo's historical weather API for daily precipitation over the
    last HISTORY_YEARS years.

    in  -> lat, lon
    out -> raw JSON response dict with a "daily" section containing dates + precipitation_sum

    Raises: RainfallDataError on any network/HTTP failure.
    """
    today = date.today()
    start_date = date(today.year - HISTORY_YEARS, 1, 1)
    end_date = date(today.year - 1, 12, 31)  # last full year, avoids partial-year data

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "precipitation_sum",
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as e:  # ValueError: non-JSON body
        raise RainfallDataError(f"Rainfall data fetch failed: {e}")


def aggregate_rainfall(raw: dict) -> RainfallResult:
    """
    Turns Open-Meteo's raw daily response into annual average + seasonal breakdown.

    in  -> raw dict with structure: {"daily": {"time": [...dates], "precipitation_sum": [...mm]}}
    out -> RainfallResult
    """
    daily = raw.get("daily", {})
    dates = daily.get("time", [])
    values = daily.get("precipitation_sum", [])

    if not dates or not values or len(dates) != len(values):
        raise RainfallDataError("Rainfall API returned malformed/empty daily data.")

    monsoon_total = 0.0
    non_monsoon_total = 0.0
    years_seen = set()

    for date_str, mm in zip(dates, values):
        if mm is None:
            continue  # Open-Meteo can return null for missing days
        year = int(date_str[:4])
        month = int(date_str[5:7])
        years_seen.add(year)

        if month in MONSOON_MONTHS:
            monsoon_total += mm
        else:
            non_monsoon_total += mm

    num_years = max(len(years_seen), 1)  # avoid divide-by-zero
    annual_avg_mm = round((monsoon_total + non_monsoon_total) / num_years, 1)

    return RainfallResult(
        annual_avg_mm=annual_avg_mm,
        seasonal={
            "monsoon_mm": round(monsoon_total / num_years, 1),
            "non_monsoon_mm": round(non_monsoon_total / num_years, 1),
        },
        data_years=num_years,
    )
