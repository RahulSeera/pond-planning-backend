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


class RainfallDataError(Exception):
    """Raised when the rainfall API call fails."""
    pass


async def get_rainfall_stats(lat: float, lon: float) -> RainfallResult:
    """
    Interface contract (unchanged from the stub - main.py doesn't need to change):
      in  -> lat, lon of the selected point
      out -> RainfallResult with annual average and seasonal breakdown

    Raises: RainfallDataError if the API call fails.
    """
    raw = await fetch_historical_rainfall(lat, lon)
    return aggregate_rainfall(raw)


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
    except httpx.HTTPError as e:
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
