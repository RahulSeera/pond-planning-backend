"""
Pydantic models = the "contract" for what goes in/out of the API.
FastAPI uses these for: (1) validating incoming requests automatically,
(2) generating the Swagger docs, (3) serializing responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


# ---------- Requests ----------

class AnalyzeRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Latitude of selected point")
    lon: float = Field(..., ge=-180, le=180, description="Longitude of selected point")
    village_id: Optional[int] = Field(None, description="Optional village reference")


class BoundingBox(BaseModel):
    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)


class AnalyzeAreaRequest(BaseModel):
    bounds: BoundingBox
    name: Optional[str] = Field("Selected Land Area", description="Optional label for the area")


# ---------- Sub-results (what each module returns internally) ----------

class TerrainResult(BaseModel):
    catchment_polygon: dict  # GeoJSON geometry
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
    rainfall: Optional[RainfallResult] = None  # nullable — rainfall can fail while terrain succeeds
    recommendation: Optional[RecommendationResult] = None
    warnings: list[str] = []


# ---------- Contour-map & Area phase ----------

class PondSite(BaseModel):
    lat: float
    lon: float


class ContourAnalysisResponse(BaseModel):
    source_filename: str
    contour_lines_parsed: int
    elevation_range_m: dict  # {"min": ..., "max": ...}
    suggested_pond_site: PondSite  # auto-discovered
    catchment_area_km2: float
    avg_slope_percent: float
    catchment_polygon: dict  # GeoJSON
    expected_water_volume_m3: Optional[float] = None
    rainfall: Optional[RainfallResult] = None
    recommendation: Optional[RecommendationResult] = None
    warnings: list[str] = []


class AreaAnalysisResponse(BaseModel):
    selected_bounds: BoundingBox
    suggested_pond_site: PondSite
    catchment_area_km2: float
    avg_slope_percent: float
    catchment_polygon: dict  # GeoJSON
    expected_water_volume_m3: float
    rainfall: Optional[RainfallResult] = None
    recommendation: Optional[RecommendationResult] = None
    warnings: list[str] = []


# ---------- Village & Search ----------

class VillageItem(BaseModel):
    id: int
    name: str
    district: Optional[str] = ""
    state: Optional[str] = ""
    lat: float
    lon: float


class VillageSearchResponse(BaseModel):
    query: str
    results: List[VillageItem]


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    uptime_seconds: float
    memory_mb: float
    pid: int
