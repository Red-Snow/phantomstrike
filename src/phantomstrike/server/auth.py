"""
PhantomStrike API authentication.

This module exists because the setting did not.

`AuthConfig.enabled` defaulted to True and `AuthConfig.api_keys` was populated
from the environment, but no route ever consulted either one — every endpoint,
including tool execution, answered any caller. The configuration described a
control that was never implemented.

Two protections are defined here:

  1. `require_api_key`  — an API-key dependency for every state-changing route.
  2. `BrowserOriginGuard` — rejects requests carrying a browser `Origin` that is
     not explicitly allowlisted, which stops drive-by requests from pages the
     operator happens to have open.

The second matters more than it looks. Binding to 127.0.0.1 feels private, but
localhost is reachable from every tab in the operator's browser. Without an
origin check, any website they visit can POST to the execution endpoint.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from phantomstrike.config import settings
from phantomstrike.utils.logging import get_logger

log = get_logger("auth")

API_KEY_HEADER = "X-API-Key"


def _key_matches(presented: str, known: list[str]) -> bool:
    """
    Constant-time comparison against every configured key.

    `hmac.compare_digest` avoids leaking key material through response timing.
    Every candidate is checked without early exit so the number of comparisons
    does not depend on which key matched.
    """
    matched = False
    for candidate in known:
        if hmac.compare_digest(presented, candidate):
            matched = True
    return matched


async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
) -> str:
    """
    FastAPI dependency enforcing API-key authentication.

    Attach to every route that executes, mutates, or discloses job data.

    Returns:
        The authenticated principal, for audit logging.

    Raises:
        HTTPException 401 when the key is missing or wrong.
    """
    if not settings.auth.enabled:
        # Explicitly disabled by the operator. Recorded so it is visible in logs
        # rather than being a silent property of the deployment.
        return "anonymous (auth disabled)"

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {API_KEY_HEADER} header",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )

    if not _key_matches(x_api_key, settings.auth.api_keys):
        client = request.client.host if request.client else "unknown"
        log.warning(f"Rejected request with invalid API key from {client}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )

    return f"key:{x_api_key[:6]}…"


class BrowserOriginGuard(BaseHTTPMiddleware):
    """
    Reject cross-origin browser requests to an API that runs commands.

    A browser attaches `Origin` to every cross-site request and forbids scripts
    from forging it. Requests from curl, the MCP client, or the CLI carry no
    `Origin` at all and pass through untouched, so this costs legitimate callers
    nothing while closing the drive-by path completely.
    """

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in settings.server.cors_origins:
            log.warning(
                f"Blocked cross-origin request from {origin} to {request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Cross-origin requests are not accepted",
                    "detail": (
                        "This API executes system commands and does not serve browser "
                        "origins. Add the origin to PHANTOMSTRIKE_CORS_ORIGINS only if "
                        "you operate the page making the request."
                    ),
                },
            )
        return await call_next(request)
