"""API routes for distribution network hierarchy and topological tree navigation."""
from fastapi import APIRouter, HTTPException, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaUpstreamError
from src.models.hierarchy import HierarchyResponse

router = APIRouter(prefix="/hierarchy", tags=["Network Hierarchy"])


@router.get(
    "",
    response_model=HierarchyResponse,
    summary="Get Complete Grid Hierarchy",
    description="Retrieve the reconstructed 7-level distribution hierarchy tree (Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT -> Meters) with summary counts and topological self-healing statistics.",
)
async def get_hierarchy(
    service: MeterServiceDep,
):
    try:
        return await service.get_hierarchy()
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
