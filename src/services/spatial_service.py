"""Spatial indexing and Geo-Proximity service using Haversine algorithm."""
import math
from typing import List, Optional
from src.models.analytics import MeterNearbyItem, SpatialQueryResponse
from src.models.meter import MeterDetail, MeterSummary


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes the great-circle distance between two points on the Earth's surface
    using the Haversine formula.
    
    Returns:
        Distance in kilometers.
    """
    # Earth radius in kilometers
    r = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class SpatialService:
    """Provides geo-proximity search and radius filtering over meter inventory.
    
    Scale Analysis:
    - Current dataset: 403 meters. In-memory linear scan + Haversine takes < 0.1ms.
    - Scale limit of approach: Works cleanly up to ~50,000 meters in memory.
    - At utility scale (100k+ to millions of meters), this linear approach will struggle
      due to O(N) CPU load. In production, migrate to an R-Tree index (e.g. libspatialindex)
      or database spatial engine (PostgreSQL + PostGIS with GiST indexing).
    """

    def find_nearby(
        self,
        meters: List[MeterDetail],
        latitude: float,
        longitude: float,
        radius_km: float = 2.0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> SpatialQueryResponse:
        """Finds meters within radius_km of (latitude, longitude), sorted by proximity."""
        results: List[MeterNearbyItem] = []

        for m in meters:
            if not m.geo:
                continue
            if status and m.install_status.value.lower() != status.lower():
                continue

            dist = haversine_distance_km(
                latitude, longitude, m.geo.latitude, m.geo.longitude
            )
            if dist <= radius_km:
                summary = MeterSummary(
                    meter_id=m.meter_id,
                    serial_no=m.serial_no,
                    make=m.make,
                    phase_type=m.phase_type,
                    install_status=m.install_status,
                    dt_code=m.dt_code,
                    install_type=m.install_type,
                    build=m.build,
                    geo=m.geo,
                )
                results.append(MeterNearbyItem(meter=summary, distance_km=round(dist, 3)))

        # Sort ascending by distance
        results.sort(key=lambda item: item.distance_km)

        trimmed = results[:limit]
        return SpatialQueryResponse(
            query_latitude=latitude,
            query_longitude=longitude,
            radius_km=radius_km,
            total_found=len(results),
            meters=trimmed,
        )
