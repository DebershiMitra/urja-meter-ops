"""API routes for smart meter discovery, details, telemetry, and coordinates."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaNotFoundError, UrjaUpstreamError
from src.models.analytics import PaginatedResponse
from src.models.meter import EnergySummary, GeoLocation, MeterDetail

router = APIRouter(prefix="/meters", tags=["Smart Meters"])


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List & Filter Smart Meters",
    description="Retrieve paginated meters with multi-attribute filtering across status, make, phase, build, DT, and full-text search.",
)
async def list_meters(
    service: MeterServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Free text search across meter ID, serial, make, DT"),
    status: Optional[str] = Query(None, description="Filter by install status: Installed, Faulty, Decommissioned"),
    phase: Optional[str] = Query(None, description="Filter by phase: single, three"),
    make: Optional[str] = Query(None, description="Filter by manufacturer (e.g. HPL, L&T, Genus, Secure, Allied)"),
    build: Optional[str] = Query(None, description="Filter by hardware generation: legacy, v2"),
    dt_code: Optional[str] = Query(None, description="Filter by Distribution Transformer code (e.g. DT-001)"),
    zone_code: Optional[str] = Query(None, description="Filter by Zone code (e.g. Z-01)"),
    feeder_code: Optional[str] = Query(None, description="Filter by Feeder code (e.g. F-001)"),
):
    try:
        return await service.get_meters(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            phase=phase,
            make=make,
            build=build,
            dt_code=dt_code,
            zone_code=zone_code,
            feeder_code=feeder_code,
        )
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get(
    "/{meter_id}",
    response_model=MeterDetail,
    summary="Get Meter Details",
    description="Retrieve full details of a specific meter, including physical specs and the complete reconstructed 7-level hierarchy.",
)
async def get_meter(
    meter_id: str,
    service: MeterServiceDep,
):
    try:
        return await service.get_meter(meter_id)
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get(
    "/{meter_id}/energy",
    response_model=EnergySummary,
    summary="Get Meter Energy Telemetry",
    description="Retrieve 337 half-hourly interval telemetry readings (7-day window) along with computed net consumption, average power factor, and voltage dip analysis.",
)
async def get_meter_energy(
    meter_id: str,
    service: MeterServiceDep,
):
    try:
        return await service.get_meter_energy(meter_id)
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get(
    "/{meter_id}/geo",
    response_model=GeoLocation,
    summary="Get Meter Geo Coordinates",
    description="Retrieve WGS84 GPS coordinates (latitude and longitude) for a meter.",
)
async def get_meter_geo(
    meter_id: str,
    service: MeterServiceDep,
):
    try:
        return await service.get_meter_geo(meter_id)
    except UrjaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
