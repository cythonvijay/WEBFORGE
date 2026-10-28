from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router
from .architecture_api import router as architecture_router
from .config import enforce_startup_settings, settings, validate_runtime_settings
from .db import check_database_readiness
from .design_api import router as design_router
from .discovery_api import router as discovery_router
from .documentation_api import router as documentation_router
from .infrastructure_verification import router as infrastructure_verification_router
from .optimization_api import router as optimization_router
from .observability import ObservabilityMiddleware, configure_logging, logger, metrics
from .prd_api import router as prd_router
from .research_api import router as research_router
from .security import SecurityMiddleware
from .security_verification import router as security_verification_router
from .strategy_api import router as strategy_router
from .ux_api import router as ux_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    enforce_startup_settings()
    logger.info("WebForge API starting", extra={"event": "startup"})
    yield
    logger.info("WebForge API shutting down cleanly", extra={"event": "shutdown"})


app = FastAPI(title="WebForge API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-Requested-With", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(SecurityMiddleware)
app.add_middleware(ObservabilityMiddleware)
app.include_router(router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(research_router, prefix="/api")
app.include_router(strategy_router, prefix="/api")
app.include_router(prd_router, prefix="/api")
app.include_router(ux_router, prefix="/api")
app.include_router(design_router, prefix="/api")
app.include_router(architecture_router, prefix="/api")
app.include_router(security_verification_router, prefix="/api")
app.include_router(infrastructure_verification_router, prefix="/api")
app.include_router(optimization_router, prefix="/api")
app.include_router(documentation_router, prefix="/api")
# Schema is managed exclusively by Alembic (`alembic upgrade head`); startup never creates tables.


@app.get("/api/health")
def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/api/health/live")
def health_live():
    """Process liveness probe: confirms the HTTP server is responsive with zero database dependency."""
    return {
        "status": "ok",
        "check": "liveness",
        "environment": settings.environment,
        "metrics": metrics.snapshot(),
    }


@app.get("/api/ready")
def ready():
    """Readiness: the database answers a query and migrations are applied."""
    db_status = check_database_readiness(verify_migrations=True)
    cfg_errors = validate_runtime_settings()
    if not db_status["ready"] or cfg_errors:
        metrics.record_readiness_failure()
        raise HTTPException(503, "Database unavailable" if db_status["database"] != "ok" else "Service not ready")
    return {"status": "ready"}


@app.get("/api/health/ready")
def health_ready():
    """Detailed readiness probe distinguishing database connectivity, migration revision alignment, and configuration."""
    db_status = check_database_readiness(verify_migrations=True)
    cfg_errors = validate_runtime_settings()
    is_ready = db_status["ready"] and not cfg_errors
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "check": "readiness",
        "environment": settings.environment,
        "checks": {
            "database": db_status["database"],
            "migrations": db_status["migrations"],
            "configuration": "ok" if not cfg_errors else "invalid",
        },
    }
    if not is_ready:
        metrics.record_readiness_failure()
        return JSONResponse(status_code=503, content=payload)
    return payload
