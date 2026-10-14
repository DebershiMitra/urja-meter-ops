"""Dependency injection providers for FastAPI."""
from typing import Annotated
from fastapi import Depends
from src.services.meter_service import MeterService

# Singleton instance for application lifecycle
_meter_service_instance: MeterService = MeterService()


def get_meter_service() -> MeterService:
    """Provides the shared MeterService singleton."""
    return _meter_service_instance


MeterServiceDep = Annotated[MeterService, Depends(get_meter_service)]
