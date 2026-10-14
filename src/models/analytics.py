"""Pydantic models for Analytics, Grid Health, and Spatial Proximity Queries."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from src.models.meter import MeterSummary


class GridOverview(BaseModel):
    total_meters: int = Field(..., description="Total smart meters indexed")
    status_distribution: Dict[str, int] = Field(..., description="Counts grouped by installStatus")
    make_distribution: Dict[str, int] = Field(..., description="Counts grouped by manufacturer")
    phase_distribution: Dict[str, int] = Field(..., description="Counts grouped by phase (single/three)")
    build_distribution: Dict[str, int] = Field(..., description="Counts grouped by hardware generation (legacy/v2)")
    total_transformers: int = Field(..., description="Total distribution transformers in network")
    operational_health_score: float = Field(
        ...,
        description="Percentage of meters installed and operating without fault (Installed / Total * 100)"
    )


class MeterNearbyItem(BaseModel):
    meter: MeterSummary = Field(..., description="Basic meter information")
    distance_km: float = Field(..., description="Geodesic distance from query coordinates in kilometers")


class SpatialQueryResponse(BaseModel):
    query_latitude: float = Field(..., description="Center latitude searched")
    query_longitude: float = Field(..., description="Center longitude searched")
    radius_km: float = Field(..., description="Search radius in kilometers")
    total_found: int = Field(..., description="Number of meters located within radius")
    meters: List[MeterNearbyItem] = Field(default_factory=list, description="Meters sorted by proximity")


class PaginatedResponse(BaseModel):
    total: int = Field(..., description="Total items matching filter criteria")
    page: int = Field(..., description="Current page index (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total calculated pages")
    data: List[Any] = Field(default_factory=list, description="Page item list")
