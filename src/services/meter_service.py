"""High-level Meter Service coordinating ingestion, indexing, querying, and analytics."""
import asyncio
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional
from src.client.exceptions import UrjaNotFoundError
from src.client.urja_client import UrjaClient
from src.config import settings
from src.models.analytics import GridOverview, PaginatedResponse, SpatialQueryResponse
from src.models.hierarchy import HierarchyResponse
from src.models.meter import (
    EnergySummary,
    GeoLocation,
    InstallStatus,
    MeterDetail,
    MeterSummary,
    PhaseType,
)
from src.models.transformer import Transformer
from src.services.cache_service import CacheService
from src.services.energy_service import EnergyService
from src.services.hierarchy_service import HierarchyService
from src.services.spatial_service import SpatialService

logger = logging.getLogger("urja.service")


class MeterService:
    """Master domain service coordinating data from the Urja Portal."""

    def __init__(
        self,
        client: Optional[UrjaClient] = None,
        cache: Optional[CacheService] = None,
        hierarchy_service: Optional[HierarchyService] = None,
        spatial_service: Optional[SpatialService] = None,
        energy_service: Optional[EnergyService] = None,
    ):
        self.client = client or UrjaClient()
        self.cache = cache or CacheService()
        self.hierarchy_service = hierarchy_service or HierarchyService()
        self.spatial_service = spatial_service or SpatialService()
        self.energy_service = energy_service or EnergyService()

        # In-memory indexes
        self._meters_by_id: Dict[str, MeterDetail] = {}
        self._meters_list: List[MeterDetail] = []
        self._transformers_by_code: Dict[str, Transformer] = {}
        self._hierarchy_cache: Optional[HierarchyResponse] = None
        self._init_lock = asyncio.Lock()
        self._is_initialized = False

    async def initialize(self, force: bool = False) -> None:
        """Initializes and hydrates in-memory index from upstream Urja portal."""
        async with self._init_lock:
            if self._is_initialized and not force:
                return

            logger.info("Ingesting full meter dataset and topology from Urja portal...")
            
            # Fetch signed bulk export and all DTs concurrently
            export_task = self.client.export_all_meters(page=1)
            dts_task = self.client.get_all_transformers()

            export_data, raw_dts = await asyncio.gather(export_task, dts_task)
            raw_meters: List[Dict[str, Any]] = export_data.get("data", [])

            logger.info("Received %d raw meters and %d DTs.", len(raw_meters), len(raw_dts))

            # 1. Build DT topology templates for self-healing
            self.hierarchy_service.build_dt_templates(raw_meters)

            # 2. Reconstruct hierarchy tree & heal corrupted records
            hierarchy_resp = self.hierarchy_service.build_hierarchy_tree(raw_meters, raw_dts)
            self._hierarchy_cache = hierarchy_resp

            # 3. Process meters into normalized Pydantic domain models
            meters_by_id: Dict[str, MeterDetail] = {}
            meters_list: List[MeterDetail] = []

            dt_meter_counts: Dict[str, Dict[str, int]] = defaultdict(
                lambda: {"total": 0, "Installed": 0, "Faulty": 0, "Decommissioned": 0}
            )

            for m in raw_meters:
                m_id = m.get("meterId", "")
                dt_code = m.get("dtCode", "")
                status_str = m.get("installStatus", "Installed")

                # Track DT stats
                if dt_code:
                    dt_meter_counts[dt_code]["total"] += 1
                    dt_meter_counts[dt_code][status_str] += 1

                # Normalize and heal hierarchy
                hierarchy, was_healed = self.hierarchy_service.normalize_and_heal_meter_hierarchy(m)

                geo = None
                raw_geo = m.get("geo")
                if raw_geo and "lat" in raw_geo and "lng" in raw_geo:
                    geo = GeoLocation(latitude=float(raw_geo["lat"]), longitude=float(raw_geo["lng"]))

                meter_detail = MeterDetail(
                    meter_id=m_id,
                    serial_no=m.get("serialNo", ""),
                    make=m.get("make", ""),
                    phase_type=PhaseType(m.get("phaseType", "single")),
                    install_status=InstallStatus(status_str),
                    dt_code=dt_code,
                    install_type=m.get("installType"),
                    build=m.get("build"),
                    geo=geo,
                    hierarchy=hierarchy,
                    is_hierarchy_repaired=was_healed,
                )
                meters_by_id[m_id] = meter_detail
                meters_list.append(meter_detail)

            # Sort list deterministically by meter_id
            meters_list.sort(key=lambda x: x.meter_id)

            # 4. Process Transformers
            transformers_by_code: Dict[str, Transformer] = {}
            for dt in raw_dts:
                code = dt["code"]
                stats = dt_meter_counts.get(code, {"total": 0, "Installed": 0, "Faulty": 0, "Decommissioned": 0})
                transformers_by_code[code] = Transformer(
                    code=code,
                    name=dt.get("name", code),
                    feeder_code=dt.get("feederCode", ""),
                    capacity_kva=int(dt.get("capacityKva", 0)),
                    meter_count=stats["total"],
                    installed_count=stats["Installed"],
                    faulty_count=stats["Faulty"],
                    decommissioned_count=stats["Decommissioned"],
                )

            self._meters_by_id = meters_by_id
            self._meters_list = meters_list
            self._transformers_by_code = transformers_by_code
            self._is_initialized = True

            logger.info(
                "Hydration complete: %d meters indexed (%d healed), %d transformers loaded.",
                len(self._meters_list),
                hierarchy_resp.stats.healed_records_count,
                len(self._transformers_by_code),
            )

    async def get_meters(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        make: Optional[str] = None,
        build: Optional[str] = None,
        dt_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        feeder_code: Optional[str] = None,
    ) -> PaginatedResponse:
        """Retrieves paginated and filtered smart meters."""
        await self.initialize()

        filtered = self._meters_list

        # Multi-attribute filtering
        if status:
            filtered = [m for m in filtered if m.install_status.value.lower() == status.lower()]
        if phase:
            filtered = [m for m in filtered if m.phase_type.value.lower() == phase.lower()]
        if make:
            filtered = [m for m in filtered if m.make.lower() == make.lower()]
        if build:
            filtered = [m for m in filtered if m.build and m.build.lower() == build.lower()]
        if dt_code:
            filtered = [m for m in filtered if m.dt_code.lower() == dt_code.lower()]
        if zone_code:
            filtered = [
                m for m in filtered
                if m.hierarchy.zone and m.hierarchy.zone.code.lower() == zone_code.lower()
            ]
        if feeder_code:
            filtered = [
                m for m in filtered
                if m.hierarchy.feeder and m.hierarchy.feeder.code.lower() == feeder_code.lower()
            ]

        # Free text search across meter ID, serial, make
        if search:
            query = search.strip().lower()
            filtered = [
                m for m in filtered
                if query in m.meter_id.lower()
                or query in m.serial_no.lower()
                or query in m.make.lower()
                or query in m.dt_code.lower()
            ]

        total = len(filtered)
        page_size = max(1, min(100, page_size))
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=page_items,
        )

    async def get_meter(self, meter_id: str) -> MeterDetail:
        """Retrieves single meter with complete normalized hierarchy."""
        await self.initialize()
        meter = self._meters_by_id.get(meter_id)
        if not meter:
            raise UrjaNotFoundError(f"Meter with ID '{meter_id}' was not found in registry.")
        return meter

    async def get_meter_energy(self, meter_id: str) -> EnergySummary:
        """Retrieves energy telemetry with intelligent caching."""
        await self.get_meter(meter_id)  # Validate meter exists

        cache_key = f"energy:{meter_id}"

        async def fetch_energy() -> EnergySummary:
            raw_readings = await self.client.get_meter_energy(meter_id)
            return self.energy_service.process_readings(meter_id, raw_readings)

        return await self.cache.get_or_set(
            cache_key,
            fetch_energy,
            ttl_seconds=settings.energy_cache_ttl_seconds,
        )

    async def get_meter_geo(self, meter_id: str) -> GeoLocation:
        """Retrieves geo coordinates for a meter."""
        meter = await self.get_meter(meter_id)
        if meter.geo:
            return meter.geo

        # Fallback to upstream geo endpoint if not present in bulk export
        raw_geo = await self.client.get_meter_geo(meter_id)
        if "latitude" in raw_geo and "longitude" in raw_geo:
            return GeoLocation(
                latitude=float(raw_geo["latitude"]),
                longitude=float(raw_geo["longitude"]),
            )
        raise UrjaNotFoundError(f"Geo coordinates not available for meter '{meter_id}'")

    async def get_transformers(
        self,
        page: int = 1,
        page_size: int = 20,
        feeder_code: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PaginatedResponse:
        """Retrieves paginated Distribution Transformers with load stats."""
        await self.initialize()

        dts = list(self._transformers_by_code.values())
        if feeder_code:
            dts = [d for d in dts if d.feeder_code.lower() == feeder_code.lower()]
        if search:
            q = search.lower()
            dts = [d for d in dts if q in d.code.lower() or q in d.name.lower()]

        total = len(dts)
        page_size = max(1, min(100, page_size))
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        items = dts[start_idx : start_idx + page_size]

        return PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=items,
        )

    async def get_hierarchy(self) -> HierarchyResponse:
        """Returns the full 7-level recursive hierarchy tree."""
        await self.initialize()
        if self._hierarchy_cache:
            return self._hierarchy_cache
        raise RuntimeError("Hierarchy service failed to initialize.")

    async def get_grid_overview(self) -> GridOverview:
        """Computes comprehensive distribution grid health analytics."""
        await self.initialize()

        status_counts = Counter(m.install_status.value for m in self._meters_list)
        make_counts = Counter(m.make for m in self._meters_list)
        phase_counts = Counter(m.phase_type.value for m in self._meters_list)
        build_counts = Counter(m.build for m in self._meters_list if m.build)

        total_meters = len(self._meters_list)
        installed = status_counts.get("Installed", 0)
        health_score = round((installed / total_meters * 100), 2) if total_meters > 0 else 0.0

        return GridOverview(
            total_meters=total_meters,
            status_distribution=dict(status_counts),
            make_distribution=dict(make_counts),
            phase_distribution=dict(phase_counts),
            build_distribution=dict(build_counts),
            total_transformers=len(self._transformers_by_code),
            operational_health_score=health_score,
        )

    async def find_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 2.0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> SpatialQueryResponse:
        """Finds meters within radius_km of coordinates."""
        await self.initialize()
        return self.spatial_service.find_nearby(
            self._meters_list,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            limit=limit,
            status=status,
        )

    async def refresh_cache(self) -> Dict[str, Any]:
        """Manually forces a fresh re-ingestion from the upstream portal."""
        await self.cache.invalidate()
        await self.initialize(force=True)
        return {
            "status": "success",
            "message": "Cache successfully purged and re-hydrated from upstream portal.",
            "total_meters": len(self._meters_list),
            "total_transformers": len(self._transformers_by_code),
        }
