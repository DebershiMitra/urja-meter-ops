"""Pydantic models for Distribution Transformers (DTs)."""
from typing import Optional
from pydantic import BaseModel, Field


class Transformer(BaseModel):
    code: str = Field(..., description="Unique Distribution Transformer code (e.g. DT-001)")
    name: str = Field(..., description="Transformer station name")
    feeder_code: str = Field(..., description="Parent 11kV Feeder code")
    capacity_kva: int = Field(..., description="Rated power capacity in kVA (e.g. 40, 63, 100, 250)")
    meter_count: int = Field(default=0, description="Total active meters connected to this DT")
    installed_count: int = Field(default=0, description="Installed meters count")
    faulty_count: int = Field(default=0, description="Faulty meters count")
    decommissioned_count: int = Field(default=0, description="Decommissioned meters count")
