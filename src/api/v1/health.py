"""System health checks and cache administration endpoints."""
import time
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from src.api.deps import MeterServiceDep
from src.client.exceptions import UrjaUpstreamError

router = APIRouter(prefix="", tags=["System & Cache"])

START_TIME = time.time()


@router.get(
    "/health",
    summary="Service Health Status",
    description="Returns platform health, uptime, upstream session state, and memory index status.",
)
async def health_check(
    service: MeterServiceDep,
) -> Dict[str, Any]:
    uptime_seconds = round(time.time() - START_TIME, 1)
    is_ready = service._is_initialized
    meter_count = len(service._meters_list) if is_ready else 0
    dt_count = len(service._transformers_by_code) if is_ready else 0

    return {
        "status": "healthy" if is_ready else "initializing",
        "uptime_seconds": uptime_seconds,
        "indexed_meters": meter_count,
        "indexed_transformers": dt_count,
        "upstream_portal": service.client.base_url,
        "session_authenticated": bool(service.client._session_token),
    }


@router.post(
    "/cache/refresh",
    summary="Purge & Refresh Cache",
    description="Manually triggers immediate re-ingestion and index hydration from the upstream Urja portal.",
)
async def refresh_cache(
    service: MeterServiceDep,
) -> Dict[str, Any]:
    try:
        return await service.refresh_cache()
    except UrjaUpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
