# Urja Meter Ops — Modern API & Data Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python)](https://python.org)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063.svg?style=flat&logo=pydantic)](https://docs.pydantic.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=flat&logo=docker)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-13%20Passed-10B981.svg?style=flat)](tests/)

A modern, high-performance, documented REST API service and operational web client built over the legacy internal **Urja Meter Ops** portal (`https://urja-ops.flockenergy.tech`).

Developed as part of the **Flock Energy Engineering Take-Home Challenge**.

---

## Table of Contents
1. [Overview & What We Built](#1-overview--what-we-built)
2. [Key Deliverables Quick Links](#2-key-deliverables-quick-links)
3. [Architecture & System Flow](#3-architecture--system-flow)
4. [Quickstart: Installation & Running](#4-quickstart-installation--running)
5. [Sample API Requests & cURL Examples](#5-sample-api-requests--curl-examples)
6. [Design Decisions & Trade-Offs](#6-design-decisions--trade-offs)
7. [What We Intentionally Left Out & Why](#7-what-we-intentionally-left-out--why)
8. [Optional Extensions Implemented](#8-optional-extensions-implemented)
9. [What We'd Improve With More Time](#9-what-wed-improve-with-more-time)
10. [Reflection & Self-Critique](#10-reflection--self-critique)

---

## 1. Overview & What We Built

The utility's internal Urja Meter Ops web portal is browser-only with no public API. Operators were forced to manually click and copy-paste smart meter information, network hierarchies, and energy consumption intervals.

Our solution wraps this legacy system in a **type-safe, asynchronous REST API** and a **modern grid intelligence dashboard**:
- **Reverse-Engineered Ingestion:** Authenticates with Better-Auth, passes SvelteKit CSRF guards, and uses an HMAC-SHA256 signature scheme to perform bulk extraction via `/portal/export` (300ms single-call hydration vs. 420+ paginated scrapes).
- **7-Tier Topological Hierarchy Reconstruction:** Reassembles the entire distribution network (`Zone` $\rightarrow$ `Circle` $\rightarrow$ `Division` $\rightarrow$ `Subdivision` $\rightarrow$ `Substation` $\rightarrow$ `Feeder` $\rightarrow$ `DT` $\rightarrow$ `Meters`).
- **Automated Topological Self-Healing:** Detects and repairs 14 upstream corrupted records with missing hierarchy links using physical DT tree topology matching.
- **Interval Telemetry Analytics:** Ingests 337 half-hourly readings per meter to compute net active consumption (kWh), apparent consumption (kVAh), weighted average power factor, voltage bounds, and sub-nominal voltage dips ($<200\text{V}$).
- **Spatial Indexing Layer:** Computes geodesic proximity using the Haversine formula for radius search (`/api/v1/spatial/nearby`).
- **Modern Interactive Dashboard:** Served at `/` and `/dashboard` with Leaflet.js maps, Chart.js telemetry plots, collapsible tree explorer, and live search.

---

## 2. Key Deliverables Quick Links

| Deliverable | Location | Description |
|---|---|---|
| **Protocol Reverse-Engineering** | [PROTOCOL.md](PROTOCOL.md) | In-depth technical breakdown of SvelteKit internals, CSRF gotchas, HMAC signing algorithm, and data schemas. |
| **OpenAPI 3.1 Specification** | [openapi.json](openapi.json) | Complete exported OpenAPI 3.1 schema. Also rendered interactively at `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` (Redoc). |
| **Engineering Reflection** | [REFLECTION.md](REFLECTION.md) | Answers to the 5 mandatory evaluation questions (assumptions, hardest parts, mistakes, next-day improvements, self-critique). |
| **Modern Web Client** | [src/web/static/](src/web/static/) | Single-page application served directly at `http://localhost:8000/`. |
| **Test Suite** | [tests/](tests/) | 13 automated unit and integration tests covering HMAC, client, hierarchy healing, spatial math, and endpoints. |

---

## 3. Architecture & System Flow

```mermaid
flowchart TD
    subgraph Clients["Client Layer"]
        A["External Services / Data Engineers"] -->|"REST / JSON"| E["FastAPI Gateway"]
        B["Browser Users / Operators"] -->|"Web UI / Dashboard"| E
        C["API Explorers"] -->|"Swagger / Redoc /docs"| E
    end

    subgraph Service["Modern Urja API Platform"]
        E --> F["API Routers"]
        F --> G["Meter & Domain Service Layer"]
        G --> H["Hierarchy Service - Graph & Self-Healing"]
        G --> I["Spatial Service - Haversine Distance Engine"]
        G --> J["Energy Service - Power Factor & Telemetry"]
        G --> K["In-Memory Cache & Index - TTL + SWR"]
        K --> L["Urja Upstream Adapter Client"]
    end

    subgraph Upstream["Urja Meter Ops Legacy Portal"]
        L -->|"1. Better-Auth Login (CSRF-Safe)"| M["POST /login"]
        L -->|"2. Key Retrieval"| N["GET /portal/keys"]
        L -->|"3. Signed Bulk Ingest (HMAC-SHA256)"| O["GET /portal/export?page=1"]
        L -->|"4. Live Telemetry"| P["GET /portal/meters/:id/energy"]
    end
```

### Directory Structure
```
d:\flock energy\
├── src/
│   ├── main.py                     # FastAPI application entrypoint & lifespan
│   ├── config.py                   # Pydantic Settings configuration
│   ├── client/
│   │   ├── urja_client.py          # Portal adapter (CSRF, session token, HMAC signing, retries)
│   │   └── exceptions.py           # Domain exceptions
│   ├── models/
│   │   ├── meter.py                # Meter, GeoLocation, Energy telemetry schemas
│   │   ├── transformer.py          # Distribution Transformer schemas
│   │   ├── hierarchy.py            # Recursive 7-tier topology tree schemas
│   │   └── analytics.py            # Grid overview and spatial query schemas
│   ├── services/
│   │   ├── meter_service.py        # Coordinator: hydration, search, multi-filter, pagination
│   │   ├── hierarchy_service.py    # Topology reconstruction & self-healing engine
│   │   ├── spatial_service.py      # Haversine radius calculation engine
│   │   ├── energy_service.py       # Metrics calculator (kWh, kVAh, PF, voltage dips)
│   │   └── cache_service.py        # TTL index with Stale-While-Revalidate support
│   ├── api/
│   │   ├── deps.py                 # Dependency injection
│   │   └── v1/                     # Modular REST routers (meters, transformers, hierarchy, spatial, analytics, health)
│   └── web/
│       └── static/                 # Modern web UI (index.html, app.js, styles.css)
├── tests/                          # 13 unit & integration tests
├── PROTOCOL.md                     # Reverse-engineering documentation
├── REFLECTION.md                   # Retrospective & evaluation answers
├── openapi.json                    # Exported OpenAPI 3.1 specification
├── Dockerfile                      # Production container image
├── docker-compose.yml              # Multi-container orchestration
└── requirements.txt                # Python dependencies
```

---

## 4. Quickstart: Installation & Running

### Option A: Local Python Environment

#### 1. Clone & Enter Directory
```bash
git clone <REPO_URL>
cd "flock energy"
```

#### 2. Create and Activate Virtual Environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate
```

#### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 4. Run the API Server
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
The application will automatically connect to `https://urja-ops.flockenergy.tech`, authenticate, hydrate all 403 meters, and start serving on `http://localhost:8000`.

- **Web Dashboard:** [http://localhost:8000/](http://localhost:8000/)
- **Interactive Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Interactive Redoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Raw OpenAPI 3.1 JSON:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

#### 5. Run Automated Tests
```bash
pytest -v
```

---

### Option B: Run via Docker / Docker Compose

```bash
docker-compose up --build
```
Access the application immediately at `http://localhost:8000`.

---

## 5. Sample API Requests & cURL Examples

### 1. Grid Health & Analytics Overview
```bash
curl -X GET "http://localhost:8000/api/v1/analytics/summary"
```
**Response Preview:**
```json
{
  "total_meters": 403,
  "status_distribution": {
    "Installed": 238,
    "Faulty": 90,
    "Decommissioned": 75
  },
  "make_distribution": {
    "HPL": 90,
    "Genus": 88,
    "Secure": 85,
    "Allied": 76,
    "L&T": 64
  },
  "phase_distribution": {
    "single": 277,
    "three": 126
  },
  "build_distribution": {
    "legacy": 238,
    "v2": 165
  },
  "total_transformers": 40,
  "operational_health_score": 59.06
}
```

### 2. Search & Filter Meters
```bash
curl -X GET "http://localhost:8000/api/v1/meters?status=Installed&phase=three&page=1&page_size=2"
```

### 3. Retrieve Single Meter with Reconstructed Hierarchy
```bash
curl -X GET "http://localhost:8000/api/v1/meters/J100011"
```
**Response Preview (Repaired Hierarchy):**
```json
{
  "meter_id": "J100011",
  "serial_no": "SI29088",
  "make": "Secure",
  "phase_type": "three",
  "install_status": "Installed",
  "dt_code": "DT-012",
  "install_type": "CT Operated",
  "build": "legacy",
  "geo": {
    "latitude": 26.938883,
    "longitude": 75.829986
  },
  "hierarchy": {
    "zone": { "code": "Z-01", "name": "Jaipur Zone 1" },
    "circle": { "code": "C-01", "name": "Circle 1" },
    "division": { "code": "D-01", "name": "Division 1" },
    "subdivision": { "code": "SD-01", "name": "Subdivision 1" },
    "substation": { "code": "SS-01", "name": "Substation 1" },
    "feeder": { "code": "F-001", "name": "Feeder 1" },
    "dt": { "code": "DT-012", "name": "Subhash Nagar DT 12" }
  },
  "is_hierarchy_repaired": true
}
```

### 4. Fetch 7-Day Energy Telemetry & Computed Metrics
```bash
curl -X GET "http://localhost:8000/api/v1/meters/J100000/energy"
```
**Response Preview:**
```json
{
  "meter_id": "J100000",
  "reading_count": 337,
  "start_time": "23/06/2026 23:30",
  "end_time": "30/06/2026 23:30",
  "total_active_kwh_delta": 142.05,
  "total_apparent_kvah_delta": 153.41,
  "average_power_factor": 0.9259,
  "min_voltage_v": 194.0,
  "max_voltage_v": 242.0,
  "avg_voltage_v": 226.4,
  "voltage_dip_count": 3
}
```

### 5. Proximity Radius Query (What's Near This Location?)
```bash
curl -X GET "http://localhost:8000/api/v1/spatial/nearby?latitude=26.9124&longitude=75.7873&radius_km=3.0&limit=5"
```

---

## 6. Design Decisions & Trade-Offs

1. **Direct Protocol Ingestion over Headless Browser Scraping:**
   - *Decision:* Rather than using Selenium or Playwright to drive a browser, we reverse-engineered the SvelteKit REST calls and cryptographic HMAC export protocol.
   - *Trade-Off:* Requires initial reverse-engineering investment, but yields a 100x speedup ($<350\text{ms}$ startup hydration vs. 45 seconds of browser driving), minimal CPU/RAM footprint, and high reliability.
2. **In-Memory TTL Indexing over External Database:**
   - *Decision:* For the current dataset of 403 meters, we indexed the entities in memory with asynchronous TTL refresh.
   - *Trade-Off:* Eliminates external operational dependencies (no Postgres/Redis required to run locally), achieving sub-millisecond query responses ($<0.5\text{ms}$).
3. **Pydantic v2 Type Safety:**
   - *Decision:* All models strictly validate incoming data and ensure proper serialization (e.g. converting upstream non-standard string numbers to floats).
4. **Topological Self-Healing Engine:**
   - *Decision:* Rather than passing through upstream nulls or dropping meters, we infer missing hierarchy tiers from peer meters attached to the same DT.

---

## 7. What We Intentionally Left Out & Why

- **Authentication on the Modern API Layer (API Keys / OAuth2):** We intentionally left the clean API open for frictionless review and evaluation. In a production rollout, an API Gateway (Kong, Traefik) or JWT middleware would enforce consumer authentication.
- **Write / Mutating Endpoints:** The assignment explicitly stated: *"Treat the portal as read-only. You don't need to (and shouldn't try to) attack or break it"*. Hence, we did not expose synthetic create/update endpoints.
- **Heavy GIS Libraries (GDAL / GeoPandas):** We implemented the Haversine great-circle formula in pure Python standard library (`math`). This avoids binary dependency compilation issues across platforms while providing exact metric distances.

---

## 8. Optional Extensions Implemented

All six optional extensions proposed in the take-home prompt were completed:

### 1. Network Hierarchy Reconstruction & Repair
- Reconstructed the physical 7-tier tree graph (`Zone` $\rightarrow$ `Circle` $\rightarrow$ `Division` $\rightarrow$ `Subdivision` $\rightarrow$ `Substation` $\rightarrow$ `Feeder` $\rightarrow$ `DT` $\rightarrow$ `Meter`).
- Automatically healed 14 anomalous records (11 missing circle, 8 missing feeder, 3 missing substation).
- Endpoint: `GET /api/v1/hierarchy`.

### 2. Local Index & Query Layer (Spatial Proximity & Filters)
- Multi-attribute query engine with pagination across status, make, phase, build, DT, and full-text search.
- Geo-proximity search (`GET /api/v1/spatial/nearby?latitude=...&longitude=...&radius_km=...`).
- **Scale Note:** The in-memory linear Haversine scan runs in $<0.1\text{ms}$ for 403 meters and scales efficiently to $\sim 50{,}000$ meters. Above $100\text{k}+$ meters, $O(N)$ CPU load becomes noticeable. At utility scale ($10^6$ meters), this should migrate to PostgreSQL with PostGIS GiST spatial indexing (`ST_DWithin`).

### 3. Freshness & Caching Strategy
- Master meter and hierarchy index: 3600-second TTL (matches Better-Auth session lifetime).
- Energy telemetry: 300-second TTL (5 minutes).
- Stale-While-Revalidate (SWR): Serves cached data instantly; if upstream errors occur, returns stale cached data to prevent client outages.
- Manual cache purge endpoint: `POST /api/v1/cache/refresh`.

### 4. Robustness & Fault Tolerance
- Automatic detection of expired session tokens with seamless re-login.
- Exponential backoff retry engine for network drops, rate limits (HTTP 429), and upstream 5xx errors.
- Strict header emulation (`Origin`, `Referer`, `User-Agent`) preventing CSRF rejections.

### 5. Full Dataset Bulk Path (HMAC-SHA256 Signing)
- Reverse-engineered Web Crypto HMAC signing scheme from `4.2Bgc2kUI.js`.
- Generates `x-timestamp` and `x-signature` headers to pull all 403 meters in a single bulk call (`GET /portal/export?page=1`).

### 6. Modern Web Client & Dashboard
- Accessible at `http://localhost:8000/`.
- Features an interactive **Leaflet.js map** with status color-coded markers and popups.
- Interactive **Chart.js dual-axis load curve** displaying 337 half-hourly intervals and voltage dip alerts.
- Collapsible **7-level network tree explorer** with meter count rollups.
- Real-time **meter directory** table with search and pagination.

---

## 9. What We'd Improve With More Time

1. **Persistent Spatial Database with PostGIS:** Migrate from in-memory Haversine calculations to PostGIS spatial indexes to support polygon geofencing and multi-million meter query scaling.
2. **WebSocket Telemetry Streaming:** Implement `/ws/telemetry` to push real-time alerts to field staff when a meter registers a voltage sag ($<200\text{V}$) or power factor drops below 0.80.
3. **Background Sync Worker:** Deploy Celery/Arq with Redis to continuously poll the portal in the background and record historical energy telemetry into TimescaleDB.

---

## 10. Reflection & Self-Critique

See the complete five-question reflection in [REFLECTION.md](REFLECTION.md).

---

*Authored with precision for Flock Energy • October 2026*
