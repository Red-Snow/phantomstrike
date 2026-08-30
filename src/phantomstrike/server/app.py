"""
PhantomStrike FastAPI Server — the core REST API and WebSocket endpoint.

Security posture
----------------
This service executes system commands. It is treated accordingly:

  * Every route that executes tools or discloses job data requires an API key.
  * Cross-origin browser requests are rejected outright. Binding to localhost is
    not isolation — every page in the operator's browser can reach 127.0.0.1.
  * Startup fails closed if authentication is enabled without configured keys,
    or if an unauthenticated shell would be exposed to the network.
  * Unhandled exceptions return an opaque reference id, never internal detail.

Universal shell access is ON by default: reaching all 600+ Kali/Parrot tools is
the purpose of this framework. It is protected by authentication, not by being
switched off.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from phantomstrike import __version__
from phantomstrike.config import settings
from phantomstrike.engagement import get_active, load_active
from phantomstrike.plugins.registry import registry
from phantomstrike.server.auth import BrowserOriginGuard, require_api_key
from phantomstrike.storage.database import init_db
from phantomstrike.utils.logging import get_logger

log = get_logger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # ── Startup ───────────────────────────────────────────────────────────
    log.info("PhantomStrike server starting…")

    # Fail closed before binding a port. An execution API that advertises
    # authentication but accepts every caller should not start at all.
    settings.auth.validate()
    settings.execution.validate(settings.auth.enabled, settings.server.host)

    if settings.engagement.file:
        load_active(settings.engagement.file)
    else:
        log.warning(
            "No engagement file loaded — targets are NOT scope-checked. "
            "Set PHANTOMSTRIKE_ENGAGEMENT=engagement.yaml to enforce authorised scope."
        )

    if not settings.auth.enabled:
        log.warning(
            "Authentication is DISABLED. Anyone who can reach this port can run "
            "tools on this host."
        )
    if settings.execution.allow_raw_shell:
        log.info(
            "Universal shell enabled — all Kali/Parrot tools are reachable via "
            "kali_shell. Access is gated by API key and the cross-origin guard."
        )
    else:
        log.info("Universal shell disabled — only tool plugins are exposed.")

    await init_db()
    count = registry.auto_discover()
    log.info(f"Loaded {count} tool plugins")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────
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

    # ── Cross-origin protection ───────────────────────────────────────────
    # Ordering note: BrowserOriginGuard is added last so it runs first, and
    # rejects disallowed origins before any other middleware sees the request.
    if settings.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.server.cors_origins,  # never "*" — see config
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Content-Type"],
        )
    app.add_middleware(BrowserOriginGuard)

    # ── Global exception handler ──────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Return a correlation id, not the exception text. Raw messages leak
        # filesystem paths, database URLs and internal structure to the caller.
        ref = uuid.uuid4().hex[:12]
        log.error(f"Unhandled error [{ref}] on {request.url.path}: {exc!r}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "reference": ref,
                "detail": "See server logs for this reference id.",
            },
        )

    # ── Register route modules ────────────────────────────────────────────
    from phantomstrike.server.routes.tools import router as tools_router
    from phantomstrike.server.routes.jobs import router as jobs_router

    # Authentication is applied at the router level so a newly added route
    # inherits it by default. Forgetting a decorator should not create a hole.
    app.include_router(tools_router, prefix="/api", dependencies=[Depends(require_api_key)])
    app.include_router(jobs_router, prefix="/api", dependencies=[Depends(require_api_key)])

    # ── Core endpoints ────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        """Liveness probe. Unauthenticated by design — discloses no tool data."""
        return {
            "status": "healthy",
            "version": __version__,
            "auth_enabled": settings.auth.enabled,
            "scope_enforced": get_active() is not None,
        }

    @app.get("/api/plugins", dependencies=[Depends(require_api_key)])
    async def list_plugins():
        return registry.summary()

    return app
