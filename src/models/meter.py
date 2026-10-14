"""Pydantic models for Meters, Geo, and Energy telemetry."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InstallStatus(str, Enum):
    INSTALLED = "Installed"
    FAULTY = "Faulty"
    DECOMMISSIONED = "Decommissioned"


class PhaseType(str, Enum):
    SINGLE = "single"
    THREE = "three"


class GeoLocation(BaseModel):
    latitude: float = Field(..., description="WGS84 Latitude")
    longitude: float = Field(..., description="WGS84 Longitude")


class HierarchyLevel(BaseModel):
    code: str = Field(..., description="Unique administrative or network code")
    name: str = Field(..., description="Human-readable node name")


class MeterHierarchy(BaseModel):
    zone: Optional[HierarchyLevel] = Field(None, description="Distribution Zone")
    circle: Optional[HierarchyLevel] = Field(None, description="Operational Circle")
    division: Optional[HierarchyLevel] = Field(None, description="Division")
    subdivision: Optional[HierarchyLevel] = Field(None, description="Sub-Division")
    substation: Optional[HierarchyLevel] = Field(None, description="Substation")
    feeder: Optional[HierarchyLevel] = Field(None, description="11kV Feeder Line")
    dt: Optional[HierarchyLevel] = Field(None, description="Distribution Transformer")


class MeterSummary(BaseModel):
    meter_id: str = Field(..., description="Unique alphanumeric Meter Identifier (e.g. J100000)")
    serial_no: str = Field(..., description="Manufacturer Serial Number")
    make: str = Field(..., description="Meter manufacturer (e.g. HPL, L&T, Genus, Secure, Allied)")
    phase_type: PhaseType = Field(..., description="Single-phase or three-phase connection")
    install_status: InstallStatus = Field(..., description="Operational status: Installed, Faulty, or Decommissioned")
    dt_code: str = Field(..., description="Assigned Distribution Transformer code")
    install_type: Optional[str] = Field(None, description="Installation type (e.g. Whole Current, CT Operated)")
    build: Optional[str] = Field(None, description="Hardware generation / firmware build (legacy or v2)")
    geo: Optional[GeoLocation] = Field(None, description="Physical coordinates")


class MeterDetail(MeterSummary):
    hierarchy: MeterHierarchy = Field(..., description="Full 7-level reconstructed network topology")
    is_hierarchy_repaired: bool = Field(
        default=False,
        description="True if missing parent hierarchy nodes were imputed from DT topology"
    )


class EnergyReading(BaseModel):
    timestamp: str = Field(..., description="Raw interval timestamp (DD/MM/YYYY HH:MM)")
    kwh: float = Field(..., description="Cumulative active energy reading (kWh)")
    kvah: float = Field(..., description="Cumulative apparent energy reading (kVAh)")
    volt_r: float = Field(..., description="R-phase voltage (Volts)")
    power_factor: Optional[float] = Field(
        None,
        description="Instantaneous/interval power factor ratio (kWh / kVAh), bounded 0.0 to 1.0"
    )


class EnergySummary(BaseModel):
    meter_id: str = Field(..., description="Meter Identifier")
    reading_count: int = Field(..., description="Total intervals recorded (typically 337 over 7 days)")
    start_time: Optional[str] = Field(None, description="First timestamp in dataset")
    end_time: Optional[str] = Field(None, description="Latest timestamp in dataset")
    total_active_kwh_delta: float = Field(..., description="Net active energy consumed over window (kWh)")
    total_apparent_kvah_delta: float = Field(..., description="Net apparent energy recorded over window (kVAh)")
    average_power_factor: float = Field(..., description="Weighted average power factor across period")
    min_voltage_v: float = Field(..., description="Minimum recorded R-phase voltage")
    max_voltage_v: float = Field(..., description="Maximum recorded R-phase voltage")
    avg_voltage_v: float = Field(..., description="Average R-phase voltage")
    voltage_dip_count: int = Field(..., description="Count of readings below standard nominal threshold (200V)")
    readings: List[EnergyReading] = Field(default_factory=list, description="Ordered interval readings")
