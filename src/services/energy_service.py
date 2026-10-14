"""Energy metrics calculation and power telemetry analytics service."""
import logging
from typing import Any, Dict, List
from src.models.meter import EnergyReading, EnergySummary

logger = logging.getLogger("urja.energy")


class EnergyService:
    """Processes 30-minute interval smart-meter energy telemetry."""

    @staticmethod
    def process_readings(meter_id: str, raw_readings: List[Dict[str, Any]]) -> EnergySummary:
        """Parses and computes operational telemetry metrics from interval readings.
        
        Calculations:
        - Active Energy consumed (kWh delta across window)
        - Apparent Energy consumed (kVAh delta across window)
        - Weighted Average Power Factor = Net kWh / Net kVAh
        - Voltage health: min, max, average, and sub-nominal voltage dips (<200V)
        """
        if not raw_readings:
            return EnergySummary(
                meter_id=meter_id,
                reading_count=0,
                start_time=None,
                end_time=None,
                total_active_kwh_delta=0.0,
                total_apparent_kvah_delta=0.0,
                average_power_factor=1.0,
                min_voltage_v=0.0,
                max_voltage_v=0.0,
                avg_voltage_v=0.0,
                voltage_dip_count=0,
                readings=[],
            )

        parsed_readings: List[EnergyReading] = []
        voltages: List[float] = []
        voltage_dips = 0

        prev_kwh = None
        prev_kvah = None

        for item in raw_readings:
            ts = item.get("timestamp", "")
            try:
                kwh = float(item.get("kwh", 0.0))
                kvah = float(item.get("kvah", 0.0))
                volt_r = float(item.get("voltR", 0.0))
            except (ValueError, TypeError):
                continue

            voltages.append(volt_r)
            if volt_r < 200.0 and volt_r > 0.0:
                voltage_dips += 1

            # Compute interval power factor if previous interval exists
            pf = None
            if prev_kwh is not None and prev_kvah is not None:
                delta_kwh = kwh - prev_kwh
                delta_kvah = kvah - prev_kvah
                if delta_kvah > 0.0001:
                    pf = min(1.0, max(0.0, round(delta_kwh / delta_kvah, 4)))

            parsed_readings.append(
                EnergyReading(
                    timestamp=ts,
                    kwh=round(kwh, 2),
                    kvah=round(kvah, 2),
                    volt_r=round(volt_r, 1),
                    power_factor=pf,
                )
            )

            prev_kwh = kwh
            prev_kvah = kvah

        # Window metrics
        first_reading = parsed_readings[0]
        last_reading = parsed_readings[-1]

        total_kwh_delta = max(0.0, round(last_reading.kwh - first_reading.kwh, 2))
        total_kvah_delta = max(0.0, round(last_reading.kvah - first_reading.kvah, 2))

        avg_pf = 1.0
        if total_kvah_delta > 0.001:
            avg_pf = min(1.0, max(0.0, round(total_kwh_delta / total_kvah_delta, 4)))

        min_v = min(voltages) if voltages else 0.0
        max_v = max(voltages) if voltages else 0.0
        avg_v = round(sum(voltages) / len(voltages), 1) if voltages else 0.0

        return EnergySummary(
            meter_id=meter_id,
            reading_count=len(parsed_readings),
            start_time=first_reading.timestamp,
            end_time=last_reading.timestamp,
            total_active_kwh_delta=total_kwh_delta,
            total_apparent_kvah_delta=total_kvah_delta,
            average_power_factor=avg_pf,
            min_voltage_v=min_v,
            max_voltage_v=max_v,
            avg_voltage_v=avg_v,
            voltage_dip_count=voltage_dips,
            readings=parsed_readings,
        )
