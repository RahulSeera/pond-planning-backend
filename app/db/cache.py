"""
Caching — DB-backed, keyed by rounded (lat, lon), per the HLD's design decision:
"cache API responses since elevation/rainfall APIs are free and rate-limited."

Rounding lat/lon to 3 decimal places groups requests within roughly the same
~100m grid cell into one cache entry — close enough that repeat clicks near
the same spot hit cache instead of re-fetching DEM/rainfall data.

CACHE_TTL_HOURS controls freshness: rainfall/terrain data doesn't change fast,
so a fairly long TTL is fine — long enough to make repeat demos fast, short
enough that the cache isn't stale forever.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.db.models import QueryCache

CACHE_TTL_HOURS = 24 * 7  # 1 week — terrain/rainfall data is effectively static at this timescale


def make_cache_key(lat: float, lon: float) -> str:
    """Rounds to 3 decimal places (~100m precision) so nearby clicks share a cache entry."""
    return f"{round(lat, 3)},{round(lon, 3)}"


def get_cached_response(db: Session, lat: float, lon: float) -> dict | None:
    """
    Returns the cached response dict if a fresh entry exists, else None.
    A stale (expired) entry is treated the same as a miss — caller will
    recompute and overwrite it via set_cached_response.
    """
    key = make_cache_key(lat, lon)
    entry = db.query(QueryCache).filter(QueryCache.cache_key == key).first()

    if entry is None:
        return None

    age = datetime.now(timezone.utc) - entry.created_at
    if age > timedelta(hours=CACHE_TTL_HOURS):
        return None  # stale — treat as a miss

    return entry.response_json


def set_cached_response(db: Session, lat: float, lon: float, response: dict) -> None:
    """
    Writes (or overwrites) the cache entry for this location.
    Uses a plain delete-then-insert instead of an upsert — simple and correct
    for this scale, avoids depending on Postgres-specific ON CONFLICT syntax.
    """
    key = make_cache_key(lat, lon)

    existing = db.query(QueryCache).filter(QueryCache.cache_key == key).first()
    if existing:
        db.delete(existing)
        db.flush()

    entry = QueryCache(cache_key=key, response_json=response)
    db.add(entry)
    db.commit()
