"""
SQLAlchemy models — the 5-table schema from the HLD:
  Village -> AnalysisRequest -> TerrainResult / RainfallResult / PondRecommendation

Geometry columns use GeoAlchemy2's Geometry type, backed by PostGIS. This is exactly
the "why PostgreSQL+PostGIS over MongoDB" decision from the HLD — these columns are
natively spatial and indexable (GiST), not just JSON blobs.
"""

from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry

from app.db.database import Base


class Village(Base):
    __tablename__ = "village"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

    requests = relationship("AnalysisRequest", back_populates="village")


class AnalysisRequest(Base):
    __tablename__ = "analysis_request"

    id = Column(Integer, primary_key=True)
    village_id = Column(Integer, ForeignKey("village.id"), nullable=True)
    point = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    village = relationship("Village", back_populates="requests")
    terrain_result = relationship("TerrainResultDB", back_populates="request", uselist=False)
    rainfall_result = relationship("RainfallResultDB", back_populates="request", uselist=False)
    recommendation = relationship("PondRecommendationDB", back_populates="request", uselist=False)


class TerrainResultDB(Base):
    __tablename__ = "terrain_result"

    request_id = Column(Integer, ForeignKey("analysis_request.id"), primary_key=True)
    catchment_polygon = Column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    area_km2 = Column(Float, nullable=False)
    avg_slope = Column(Float, nullable=False)

    request = relationship("AnalysisRequest", back_populates="terrain_result")


class RainfallResultDB(Base):
    __tablename__ = "rainfall_result"

    request_id = Column(Integer, ForeignKey("analysis_request.id"), primary_key=True)
    annual_avg_mm = Column(Float, nullable=False)
    seasonal_json = Column(JSON, nullable=False)
    data_years = Column(Integer, nullable=False)

    request = relationship("AnalysisRequest", back_populates="rainfall_result")


class PondRecommendationDB(Base):
    __tablename__ = "pond_recommendation"

    request_id = Column(Integer, ForeignKey("analysis_request.id"), primary_key=True)
    runoff_m3 = Column(Float, nullable=False)
    depth_m = Column(Float, nullable=False)
    surface_area_m2 = Column(Float, nullable=False)
    capacity_m3 = Column(Float, nullable=False)
    suitability_score = Column(Float, nullable=False)

    request = relationship("AnalysisRequest", back_populates="recommendation")


class QueryCache(Base):
    """
    DB-backed cache — keyed by rounded (lat, lon), per the HLD's caching design.
    Chosen over Redis to avoid standing up a second service for a course-scale
    project; the same idea (cache the whole consolidated result, keyed by a
    rounded location) applies regardless of which store backs it.
    """
    __tablename__ = "query_cache"

    cache_key = Column(String, primary_key=True)  # e.g. "21.200,81.600"
    response_json = Column(JSON, nullable=False)  # the full AnalyzeResponse, cached as-is
    created_at = Column(DateTime(timezone=True), server_default=func.now())
