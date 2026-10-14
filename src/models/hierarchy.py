"""Pydantic models for Network Hierarchy and Grid Topology."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HierarchyNode(BaseModel):
    code: str = Field(..., description="Node unique identifier")
    name: str = Field(..., description="Node readable name")
    type: str = Field(..., description="Hierarchy level type: zone, circle, division, subdivision, substation, feeder, dt")
    meter_count: int = Field(default=0, description="Number of meters attached within this subtree")
    children: List["HierarchyNode"] = Field(default_factory=list, description="Child nodes in distribution tree")


HierarchyNode.model_rebuild()


class HierarchyStats(BaseModel):
    total_zones: int = Field(..., description="Count of distinct distribution zones")
    total_circles: int = Field(..., description="Count of distinct circles")
    total_divisions: int = Field(..., description="Count of distinct divisions")
    total_subdivisions: int = Field(..., description="Count of distinct subdivisions")
    total_substations: int = Field(..., description="Count of distinct substations")
    total_feeders: int = Field(..., description="Count of distinct 11kV feeders")
    total_dts: int = Field(..., description="Count of distinct distribution transformers")
    total_meters: int = Field(..., description="Total meters connected")
    healed_records_count: int = Field(..., description="Meters whose hierarchy gaps were automatically repaired")


class HierarchyResponse(BaseModel):
    stats: HierarchyStats = Field(..., description="Summary statistics across all tiers")
    tree: List[HierarchyNode] = Field(..., description="Root zone nodes with recursive child branches")
