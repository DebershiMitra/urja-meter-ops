"""Integration tests for FastAPI endpoints using TestClient."""
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verifies service health check response."""
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "uptime_seconds" in data


def test_analytics_summary_endpoint():
    """Verifies grid overview analytics."""
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert "total_meters" in data
    assert data["total_meters"] > 0
    assert "operational_health_score" in data


def test_meters_list_endpoint():
    """Verifies paginated meter listing and filtering."""
    res = client.get("/api/v1/meters?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["data"]) <= 10
    assert data["total"] > 0


def test_meter_detail_endpoint():
    """Verifies single meter detail retrieval."""
    # First get one meter id from list
    list_res = client.get("/api/v1/meters?page=1&page_size=1")
    assert list_res.status_code == 200
    meter_id = list_res.json()["data"][0]["meter_id"]

    detail_res = client.get(f"/api/v1/meters/{meter_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["meter_id"] == meter_id
    assert "hierarchy" in detail_data


def test_hierarchy_endpoint():
    """Verifies reconstructed hierarchy tree."""
    res = client.get("/api/v1/hierarchy")
    assert res.status_code == 200
    data = res.json()
    assert "stats" in data
    assert "tree" in data
    assert data["stats"]["total_zones"] > 0
    assert data["stats"]["healed_records_count"] >= 14


def test_spatial_nearby_endpoint():
    """Verifies spatial radius query."""
    res = client.get("/api/v1/spatial/nearby?latitude=26.9124&longitude=75.7873&radius_km=10.0")
    assert res.status_code == 200
    data = res.json()
    assert "total_found" in data
    assert "meters" in data
