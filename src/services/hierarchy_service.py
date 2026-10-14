"""Service for reconstructing utility network hierarchy and self-healing missing data."""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from src.models.hierarchy import HierarchyNode, HierarchyResponse, HierarchyStats
from src.models.meter import HierarchyLevel, MeterHierarchy

logger = logging.getLogger("urja.hierarchy")

HIERARCHY_TIERS = ["zone", "circle", "division", "subdivision", "substation", "feeder", "dt"]


class HierarchyService:
    """Reconstructs the 7-level distribution network hierarchy:
    Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT -> Meter.
    
    Self-Healing Engine:
    Addresses real-world data corruption where upstream records have missing hierarchy nodes
    (e.g. 11 meters missing circle, 8 missing feeder, 3 missing substation).
    Uses DT topological grouping to impute missing parent links from peer meters.
    """

    def __init__(self):
        # Maps dt_code -> complete MeterHierarchy dictionary template
        self._dt_topology_templates: Dict[str, Dict[str, Dict[str, str]]] = {}

    def build_dt_templates(self, raw_meters: List[Dict[str, Any]]) -> None:
        """Learns the full topological upstream path for each Distribution Transformer (DT)
        from meters with complete hierarchy records.
        """
        for m in raw_meters:
            dt_code = m.get("dtCode")
            h = m.get("hierarchy", {})
            if not dt_code:
                continue

            # Check if this meter has all 7 tiers populated
            is_complete = all(
                h.get(tier) and h[tier].get("code") and h[tier].get("name")
                for tier in HIERARCHY_TIERS
            )
            if is_complete and dt_code not in self._dt_topology_templates:
                self._dt_topology_templates[dt_code] = {
                    tier: {
                        "code": str(h[tier]["code"]),
                        "name": str(h[tier]["name"]),
                    }
                    for tier in HIERARCHY_TIERS
                }

        logger.info(
            "Built complete hierarchy topology templates for %d DTs.",
            len(self._dt_topology_templates),
        )

    def normalize_and_heal_meter_hierarchy(
        self, raw_meter: Dict[str, Any]
    ) -> Tuple[MeterHierarchy, bool]:
        """Validates and heals an individual meter's hierarchy structure.
        
        Returns:
            Tuple of (MeterHierarchy model, boolean indicating if healing was applied).
        """
        raw_h = raw_meter.get("hierarchy", {}) or {}
        dt_code = raw_meter.get("dtCode")
        healed = False

        template = self._dt_topology_templates.get(dt_code, {})

        normalized: Dict[str, Optional[HierarchyLevel]] = {}
        for tier in HIERARCHY_TIERS:
            node_data = raw_h.get(tier)
            if node_data and node_data.get("code") and node_data.get("name"):
                normalized[tier] = HierarchyLevel(
                    code=str(node_data["code"]),
                    name=str(node_data["name"]),
                )
            elif template.get(tier):
                # Impute missing node from DT topology template
                healed_node = template[tier]
                normalized[tier] = HierarchyLevel(
                    code=healed_node["code"],
                    name=healed_node["name"],
                )
                healed = True
            else:
                normalized[tier] = None

        return MeterHierarchy(**normalized), healed

    def build_hierarchy_tree(
        self,
        meters: List[Dict[str, Any]],
        dt_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> HierarchyResponse:
        """Constructs a strict recursive tree graph from the normalized meters."""
        # Index DT metadata if available
        dt_name_map = {}
        if dt_metadata:
            for dt in dt_metadata:
                dt_name_map[dt["code"]] = dt.get("name", dt["code"])

        # Track unique entities at each tier for stats
        unique_entities = {tier: set() for tier in HIERARCHY_TIERS}
        healed_count = 0

        # Build adjacency maps: (parent_tier, parent_code) -> dict of child_code -> child_name
        parent_to_children: Dict[Tuple[str, str], Dict[str, Tuple[str, str]]] = defaultdict(dict)
        root_zones: Dict[str, str] = {}
        dt_meter_counts: Dict[str, int] = defaultdict(int)

        for m in meters:
            hierarchy, was_healed = self.normalize_and_heal_meter_hierarchy(m)
            if was_healed:
                healed_count += 1

            h_dict = hierarchy.model_dump()
            prev_tier = None
            prev_code = None

            for tier in HIERARCHY_TIERS:
                level_obj = h_dict.get(tier)
                if not level_obj:
                    continue
                code = level_obj["code"]
                name = level_obj["name"]
                unique_entities[tier].add(code)

                if prev_tier is None:
                    # Root zone
                    root_zones[code] = name
                else:
                    # Child link: (prev_tier, prev_code) -> (code, name, tier)
                    parent_to_children[(prev_tier, prev_code)][code] = (name, tier)

                prev_tier = tier
                prev_code = code

            if hierarchy.dt:
                dt_meter_counts[hierarchy.dt.code] += 1

        # Recursive builder
        def assemble_node(node_type: str, code: str, name: str) -> HierarchyNode:
            child_defs = parent_to_children.get((node_type, code), {})
            children_nodes = []
            subtree_meter_count = dt_meter_counts.get(code, 0) if node_type == "dt" else 0

            for child_code, (child_name, child_type) in child_defs.items():
                child_node = assemble_node(child_type, child_code, child_name)
                children_nodes.append(child_node)
                subtree_meter_count += child_node.meter_count

            return HierarchyNode(
                code=code,
                name=name,
                type=node_type,
                meter_count=subtree_meter_count,
                children=children_nodes,
            )

        tree = [assemble_node("zone", z_code, z_name) for z_code, z_name in root_zones.items()]

        stats = HierarchyStats(
            total_zones=len(unique_entities["zone"]),
            total_circles=len(unique_entities["circle"]),
            total_divisions=len(unique_entities["division"]),
            total_subdivisions=len(unique_entities["subdivision"]),
            total_substations=len(unique_entities["substation"]),
            total_feeders=len(unique_entities["feeder"]),
            total_dts=len(unique_entities["dt"]),
            total_meters=len(meters),
            healed_records_count=healed_count,
        )

        return HierarchyResponse(stats=stats, tree=tree)
