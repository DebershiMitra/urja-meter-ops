"""API routes for distribution network analytics and health scoring."""
from fastapi import APIRouter, HTTPException, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaUpstreamError
from src.models.analytics import GridOverview

router = APIRouter(prefix="/analytics", tags=["Analytics & Health"])


@router.get(
    "/summary",
    response_model=GridOverview,
    summary="Get Grid Operational Summary",
    description="High-level health and asset distribution: breakdown of meters by status, make, phase, build, and overall network operational score.",
)
async def get_grid_overview(
    service: MeterServiceDep,
):
    try:
        return await service.get_grid_overview()
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
