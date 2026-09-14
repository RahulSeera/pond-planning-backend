"""
Pydantic models = the "contract" for what goes in/out of the API.
FastAPI uses these for: (1) validating incoming requests automatically,
(2) generating the Swagger docs, (3) serializing responses.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ---------- Requests ----------

class AnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude of selected point")
    lon: float = Field(..., ge=-180, le=180, description="Longitude of selected point")
    village_id: Optional[int] = Field(None, description="Optional village reference")


# ---------- Sub-results (what each module returns internally) ----------

class TerrainResult(BaseModel):
    catchment_polygon: dict  # GeoJSON geometry, kept generic for now
    area_km2: float
    avg_slope: float


class RainfallResult(BaseModel):
    annual_avg_mm: float
    seasonal: dict
    data_years: int


class RecommendationResult(BaseModel):
    runoff_m3: float
    depth_m: float
    surface_area_m2: float
    capacity_m3: float
    suitability_score: float


# ---------- Final combined response ----------

class AnalyzeResponse(BaseModel):
    request_id: int
    lat: float
    lon: float
    terrain: TerrainResult
    rainfall: RainfallResult | None  # nullable — rainfall can fail while terrain succeeds
    recommendation: RecommendationResult | None
    warnings: list[str] = []


# ---------- Contour-map phase (POST /analyzeContour) ----------

class PondSite(BaseModel):
    lat: float
    lon: float


class ContourAnalysisResponse(BaseModel):
    source_filename: str
    contour_lines_parsed: int
    elevation_range_m: dict  # {"min": ..., "max": ...} — from the actual parsed contours, not hardcoded
    suggested_pond_site: PondSite  # auto-discovered, not user-provided
    catchment_area_km2: float
    avg_slope_percent: float
    catchment_polygon: dict  # GeoJSON
    warnings: list[str] = []
