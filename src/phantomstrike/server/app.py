"""
PhantomStrike FastAPI Server — the core REST API and WebSocket endpoint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from phantomstrike import __version__
from phantomstrike.config import settings
from phantomstrike.plugins.registry import registry
from phantomstrike.storage.database import init_db
from phantomstrike.utils.logging import get_logger

log = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ───────────────────────────────────────────────────────────
    log.info("PhantomStrike server starting…")
    await init_db()
    count = registry.auto_discover()
    log.info(f"Loaded {count} tool plugins")
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────
    log.info("PhantomStrike server shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="PhantomStrike AI",
        description="AI-powered MCP cybersecurity framework with modular tool plugins.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ──────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.error(f"Unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": str(exc)},
        )

    # ── Register route modules ────────────────────────────────────────────
    from phantomstrike.server.routes.tools import router as tools_router
    from phantomstrike.server.routes.jobs import router as jobs_router

    app.include_router(tools_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")

    # ── Core endpoints ────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": __version__,
            "plugins": registry.summary(),
            "queue": None,  # Will be enriched when queue is running
        }

    @app.get("/api/plugins")
    async def list_plugins():
        return registry.summary()

    return app
