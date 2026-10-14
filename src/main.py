"""Main FastAPI application entry point for Urja Meter Ops Modern API Platform."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.api.deps import get_meter_service
from src.api.v1.analytics import router as analytics_router
from src.api.v1.health import router as health_router
from src.api.v1.hierarchy import router as hierarchy_router
from src.api.v1.meters import router as meters_router
from src.api.v1.spatial import router as spatial_router
from src.api.v1.transformers import router as transformers_router
from src.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("urja.main")

STATIC_DIR = Path(__file__).parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.
    
    Proactively hydrates in-memory index from upstream Urja Portal on startup
    and exports openapi.json.
    """
    logger.info("Starting Urja Meter Ops Modern API service...")
    service = get_meter_service()
    try:
        # Background or non-blocking initial hydration
        asyncio.create_task(service.initialize())
    except Exception as e:
        logger.error("Initial hydration error: %s", str(e))

    # Export openapi.json to project root for submission deliverable
    try:
        openapi_schema = app.openapi()
        root_openapi_path = Path(__file__).parent.parent / "openapi.json"
        with open(root_openapi_path, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, indent=2)
        logger.info("Exported OpenAPI schema to %s", root_openapi_path)
    except Exception as e:
        logger.warning("Could not auto-write openapi.json on startup: %s", str(e))

    yield

    logger.info("Shutting down Urja Modern API service...")
    await service.client.close()


app = FastAPI(
    title="Urja Meter Ops Modern API Platform",
    description="""
# Modern, High-Performance REST API for Urja Meter Ops

This platform wraps the legacy browser-only Urja Meter Ops web portal into a clean, typed,
resilient REST API service.

### Key Capabilities:
- **Comprehensive Meter Directory**: Multi-attribute filtering, free-text search, and pagination.
- **7-Tier Network Hierarchy Reconstruction**: Full distribution tree (Zone -> Circle -> Division -> Subdivision -> Substation -> Feeder -> DT -> Meters) with topological self-healing of incomplete records.
- **Interval Energy Telemetry**: 337 half-hourly telemetry readings with computed power factor and voltage health metrics.
- **Spatial Indexing**: Geodesic proximity search using the Haversine algorithm.
- **Interactive Web Dashboard**: Live map, network tree explorer, and interactive energy charts served at `/dashboard`.
- **Fault-Tolerant Upstream Adapter**: Automatic Better-Auth re-login, SvelteKit CSRF token management, and HMAC-SHA256 request signing.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for third-party consumers and frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 routers
app.include_router(meters_router, prefix="/api/v1")
app.include_router(transformers_router, prefix="/api/v1")
app.include_router(hierarchy_router, prefix="/api/v1")
app.include_router(spatial_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")


# Mount static web UI assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serves the modern web client dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        "<h1>Urja Meter Ops Modern API</h1><p>Visit <a href='/docs'>Swagger UI /docs</a> or <a href='/redoc'>Redoc /redoc</a>.</p>"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=settings.debug)
