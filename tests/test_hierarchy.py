"""Unit tests for hierarchy reconstruction and self-healing missing data."""
import pytest
from src.services.hierarchy_service import HierarchyService


def test_hierarchy_self_healing():
    """Verifies that meters missing hierarchy tiers are healed from DT topology templates."""
    service = HierarchyService()

    # Raw meters with a complete DT template and an incomplete peer meter
    complete_meter = {
        "meterId": "M-101",
        "dtCode": "DT-001",
        "hierarchy": {
            "zone": {"code": "Z-01", "name": "Zone North"},
            "circle": {"code": "C-01", "name": "Circle 1"},
            "division": {"code": "D-01", "name": "Division 1"},
            "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
            "substation": {"code": "SS-01", "name": "Substation 1"},
            "feeder": {"code": "F-01", "name": "Feeder 1"},
            "dt": {"code": "DT-001", "name": "Transformer 1"},
        },
    }

    incomplete_meter = {
        "meterId": "M-102",
        "dtCode": "DT-001",
        # Missing circle and feeder
        "hierarchy": {
            "zone": {"code": "Z-01", "name": "Zone North"},
            "circle": None,
            "division": {"code": "D-01", "name": "Division 1"},
            "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
            "substation": {"code": "SS-01", "name": "Substation 1"},
            "feeder": None,
            "dt": {"code": "DT-001", "name": "Transformer 1"},
        },
    }

    # Step 1: Learn templates
    service.build_dt_templates([complete_meter])

    # Step 2: Validate healing
    healed_hierarchy, was_healed = service.normalize_and_heal_meter_hierarchy(incomplete_meter)
    assert was_healed is True
    assert healed_hierarchy.circle is not None
    assert healed_hierarchy.circle.code == "C-01"
    assert healed_hierarchy.feeder is not None
    assert healed_hierarchy.feeder.code == "F-01"


def test_hierarchy_tree_construction():
    """Verifies recursive tree assembly from flat meters."""
    service = HierarchyService()
    meters = [
        {
            "meterId": f"M-{i}",
            "dtCode": "DT-001",
            "hierarchy": {
                "zone": {"code": "Z-01", "name": "Zone 1"},
                "circle": {"code": "C-01", "name": "Circle 1"},
                "division": {"code": "D-01", "name": "Division 1"},
                "subdivision": {"code": "SD-01", "name": "Subdivision 1"},
                "substation": {"code": "SS-01", "name": "Substation 1"},
                "feeder": {"code": "F-01", "name": "Feeder 1"},
                "dt": {"code": "DT-001", "name": "Transformer 1"},
            },
        }
        for i in range(5)
    ]

    service.build_dt_templates(meters)
    resp = service.build_hierarchy_tree(meters)

    assert resp.stats.total_zones == 1
    assert resp.stats.total_dts == 1
    assert resp.stats.total_meters == 5
    assert len(resp.tree) == 1
    assert resp.tree[0].code == "Z-01"
    assert resp.tree[0].meter_count == 5
