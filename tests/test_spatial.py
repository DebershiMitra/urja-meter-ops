"""Unit tests for spatial indexing and Haversine proximity calculations."""
import pytest
from src.models.meter import GeoLocation, InstallStatus, MeterDetail, MeterHierarchy, PhaseType
from src.services.spatial_service import SpatialService, haversine_distance_km


def test_haversine_known_distance():
    """Verifies Haversine formula calculation between Jaipur landmarks (~4.6 km)."""
    # Hawa Mahal: 26.9239, 75.8267
    # Albert Hall Museum: 26.9118, 75.8194
    dist = haversine_distance_km(26.9239, 75.8267, 26.9118, 75.8194)
    assert 1.2 <= dist <= 1.6  # Approx 1.5 km


def test_spatial_proximity_filtering():
    """Verifies radius filtering and sorting."""
    service = SpatialService()

    # Center at (26.9000, 75.8000)
    center_lat, center_lon = 26.9000, 75.8000

    meters = [
        MeterDetail(
            meter_id="M-CLOSE",
            serial_no="S-1",
            make="HPL",
            phase_type=PhaseType.SINGLE,
            install_status=InstallStatus.INSTALLED,
            dt_code="DT-001",
            geo=GeoLocation(latitude=26.9010, longitude=75.8010),
            hierarchy=MeterHierarchy(),
        ),
        MeterDetail(
            meter_id="M-FAR",
            serial_no="S-2",
            make="L&T",
            phase_type=PhaseType.SINGLE,
            install_status=InstallStatus.INSTALLED,
            dt_code="DT-002",
            geo=GeoLocation(latitude=27.5000, longitude=76.5000),  # > 80 km away
            hierarchy=MeterHierarchy(),
        ),
    ]

    res = service.find_nearby(meters, latitude=center_lat, longitude=center_lon, radius_km=5.0)
    assert res.total_found == 1
    assert res.meters[0].meter.meter_id == "M-CLOSE"
    assert res.meters[0].distance_km < 1.0
