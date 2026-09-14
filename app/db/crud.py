"""
CRUD functions — the functions main.py calls to persist an analysis and fetch it back.
Keeps main.py from needing to know any SQLAlchemy/SQL details directly.
"""

from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point, shape

from app.db import models
from app.schemas import TerrainResult, RainfallResult, RecommendationResult


def create_analysis_request(db: Session, lat: float, lon: float, village_id: int | None = None) -> models.AnalysisRequest:
    point_wkb = from_shape(Point(lon, lat), srid=4326)  # note: Point(x=lon, y=lat) — GIS convention
    req = models.AnalysisRequest(village_id=village_id, point=point_wkb)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def save_terrain_result(db: Session, request_id: int, terrain: TerrainResult) -> None:
    polygon_wkb = None
    if terrain.catchment_polygon and terrain.catchment_polygon.get("coordinates"):
        try:
            polygon_wkb = from_shape(shape(terrain.catchment_polygon), srid=4326)
        except Exception:
            polygon_wkb = None  # malformed geometry — store the numeric results anyway

    row = models.TerrainResultDB(
        request_id=request_id,
        catchment_polygon=polygon_wkb,
        area_km2=terrain.area_km2,
        avg_slope=terrain.avg_slope,
    )
    db.add(row)
    db.commit()


def save_rainfall_result(db: Session, request_id: int, rainfall: RainfallResult) -> None:
    row = models.RainfallResultDB(
        request_id=request_id,
        annual_avg_mm=rainfall.annual_avg_mm,
        seasonal_json=rainfall.seasonal,
        data_years=rainfall.data_years,
    )
    db.add(row)
    db.commit()


def save_recommendation(db: Session, request_id: int, rec: RecommendationResult) -> None:
    row = models.PondRecommendationDB(
        request_id=request_id,
        runoff_m3=rec.runoff_m3,
        depth_m=rec.depth_m,
        surface_area_m2=rec.surface_area_m2,
        capacity_m3=rec.capacity_m3,
        suitability_score=rec.suitability_score,
    )
    db.add(row)
    db.commit()


def get_analysis_by_id(db: Session, request_id: int) -> models.AnalysisRequest | None:
    return db.query(models.AnalysisRequest).filter(models.AnalysisRequest.id == request_id).first()
