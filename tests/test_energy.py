"""Unit tests for energy telemetry parsing and power factor analytics."""
import pytest
from src.services.energy_service import EnergyService


def test_energy_metrics_calculation():
    """Verifies interval delta, power factor, and voltage analysis."""
    raw_readings = [
        {"timestamp": "24/06/2026 00:00", "kwh": "100.0", "kvah": "110.0", "voltR": "230"},
        {"timestamp": "24/06/2026 00:30", "kwh": "105.0", "kvah": "116.0", "voltR": "195"},  # Voltage dip (<200V)
        {"timestamp": "24/06/2026 01:00", "kwh": "110.0", "kvah": "122.0", "voltR": "228"},
    ]

    summary = EnergyService.process_readings("J100000", raw_readings)

    assert summary.meter_id == "J100000"
    assert summary.reading_count == 3
    assert summary.total_active_kwh_delta == 10.0  # 110 - 100
    assert summary.total_apparent_kvah_delta == 12.0  # 122 - 110
    # Power factor = 10 / 12 = 0.8333
    assert 0.83 <= summary.average_power_factor <= 0.84
    assert summary.min_voltage_v == 195.0
    assert summary.max_voltage_v == 230.0
    assert summary.voltage_dip_count == 1
