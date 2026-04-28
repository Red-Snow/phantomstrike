"""
PhantomStrike Tool Routes — REST API for executing security tools.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from phantomstrike.execution.runner import runner
from phantomstrike.execution.queue import job_queue
from phantomstrike.plugins.registry import registry
from phantomstrike.storage.database import save_result
from phantomstrike.utils.logging import get_logger

log = get_logger("routes.tools")

router = APIRouter(tags=["tools"])


class ToolExecuteRequest(BaseModel):
    """Request body for tool execution."""
    tool: str
    params: dict[str, Any] = {}
    async_mode: bool = False
    timeout: Optional[int] = None


class ToolExecuteResponse(BaseModel):
    """Response for tool execution."""
    success: bool
    job_id: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@router.post("/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool(req: ToolExecuteRequest):
    """
    Execute a security tool.

    If async_mode=True, returns a job_id immediately.
    Otherwise, blocks until the tool completes and returns results.
    """
    plugin = registry.get(req.tool)
    if not plugin:
        available = registry.get_names()
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{req.tool}' not found. Available: {available}",
        )

    if not plugin.is_available():
        missing = plugin.get_missing_binaries()
        raise HTTPException(
            status_code=422,
            detail=f"Tool '{req.tool}' is not installed. Missing binaries: {missing}",
        )

    # ── Async mode → submit to queue ──────────────────────────────────────
    if req.async_mode:
        job_id = await job_queue.submit(plugin, req.params)
        return ToolExecuteResponse(success=True, job_id=job_id)

    # ── Sync mode → run and wait ──────────────────────────────────────────
    result = await runner.run(plugin, req.params, timeout=req.timeout)

    # Persist to database
    try:
        await save_result(result)
    except Exception as e:
        log.warning(f"Failed to save result to database: {e}")

    return ToolExecuteResponse(
        success=result.success,
        result=result.to_dict(),
        error=result.error_message if not result.success else None,
    )


@router.get("/tools")
async def list_tools():
    """List all available tools and their status."""
    return registry.summary()


@router.get("/tools/{tool_name}")
async def get_tool_info(tool_name: str):
    """Get detailed info about a specific tool."""
    plugin = registry.get(tool_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return plugin.get_metadata()


@router.get("/tools/{tool_name}/schema")
async def get_tool_schema(tool_name: str):
    """Get the input schema for a tool (useful for AI agents)."""
    plugin = registry.get(tool_name)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return plugin.InputSchema.model_json_schema()
