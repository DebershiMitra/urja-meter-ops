"""API routes for Distribution Transformers (DTs)."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaUpstreamError
from src.models.analytics import PaginatedResponse

router = APIRouter(prefix="/transformers", tags=["Transformers"])


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List Distribution Transformers",
    description="Retrieve paginated list of Distribution Transformers with capacity and real-time attached meter operational status counts.",
)
async def list_transformers(
    service: MeterServiceDep,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    feeder_code: Optional[str] = Query(None, description="Filter by parent Feeder code"),
    search: Optional[str] = Query(None, description="Search across DT code or name"),
):
    try:
        return await service.get_transformers(
            page=page,
            page_size=page_size,
            feeder_code=feeder_code,
            search=search,
        )
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
