"""API routes for spatial proximity queries and radius searching."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaUpstreamError
from src.models.analytics import SpatialQueryResponse

router = APIRouter(prefix="/spatial", tags=["Spatial & Location"])


@router.get(
    "/nearby",
    response_model=SpatialQueryResponse,
    summary="Find Meters Near GPS Coordinates",
    description="Calculates geodesic distance using the Haversine formula and returns smart meters within a radial distance (km) of specified latitude/longitude.",
)
async def find_nearby_meters(
    service: MeterServiceDep,
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Center GPS Latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Center GPS Longitude"),
    radius_km: float = Query(2.0, ge=0.01, le=100.0, description="Radius boundary in kilometers"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    status: Optional[str] = Query(None, description="Optional filter by install status: Installed, Faulty, Decommissioned"),
):
    try:
        return await service.find_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            limit=limit,
            status=status,
        )
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
