"""
PhantomStrike MCP Client — the bridge between AI agents and security tools.

This module auto-generates MCP tool definitions from the plugin registry.
Instead of manually writing 100+ tool functions (like HexStrike does),
we dynamically create them from plugin metadata.

Supports two modes:
1. LOCAL mode  — runs tools directly on the local machine (default)
2. REMOTE mode — delegates to a PhantomStrike API server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from phantomstrike import __version__
from phantomstrike.config import settings
from phantomstrike.execution.runner import runner
from phantomstrike.plugins.base import BaseToolPlugin
from phantomstrike.plugins.registry import registry
from phantomstrike.storage.database import init_db, save_result
from phantomstrike.utils.logging import get_logger, print_banner, setup_logging

log = get_logger("mcp")


def create_mcp_server(mode: str = "local", server_url: str = "") -> FastMCP:
    """
    Create the MCP server with auto-generated tool definitions.

    Args:
        mode: 'local' (direct execution) or 'remote' (API delegation).
        server_url: PhantomStrike API server URL (for remote mode).

    Returns:
        Configured FastMCP instance ready to run.
    """
    mcp = FastMCP("phantomstrike")

    if mode == "remote":
        _register_remote_tools(mcp, server_url)
    else:
        _register_local_tools(mcp)

    # ── Utility tools (always available) ──────────────────────────────────

    @mcp.tool()
    async def list_tools() -> dict[str, Any]:
        """
        List all available PhantomStrike security tools and their status.

        Returns a summary of all registered tools, categories, and availability.
        Use this to discover what tools are available before running scans.
        """
        return registry.summary()

    @mcp.tool()
    async def tool_info(tool_name: str) -> dict[str, Any]:
        """
        Get detailed information about a specific security tool.

        Args:
            tool_name: Name of the tool (e.g., 'nmap', 'nuclei', 'gobuster')

        Returns:
            Tool metadata including description, parameters, and availability.
        """
        plugin = registry.get(tool_name)
        if not plugin:
            return {"error": f"Tool '{tool_name}' not found", "available_tools": registry.get_names()}
        return plugin.get_metadata()

    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """
        Check PhantomStrike system health — server status, available tools,
        and database connectivity.
        """
        return {
            "status": "healthy",
            "version": __version__,
            "mode": mode,
            "total_plugins": len(registry),
            "available_plugins": len(registry.get_available()),
            "categories": {
                cat: len(plugins)
                for cat, plugins in _group_by_category().items()
            },
        }

    return mcp


def _group_by_category() -> dict[str, list[str]]:
    """Group plugin names by category."""
    groups: dict[str, list[str]] = {}
    for name, plugin in registry.get_all().items():
        cat = plugin.category.value
        groups.setdefault(cat, []).append(name)
    return groups


# ── Local mode tool registration ──────────────────────────────────────────────

def _register_local_tools(mcp: FastMCP) -> None:
    """
    Register MCP tools that execute directly on the local machine.

    Each plugin gets a dynamically created async function that:
    1. Validates parameters via the plugin's InputSchema
    2. Runs the tool via the async runner
    3. Saves results to the database
    4. Returns structured results to the AI agent
    """
    for name, plugin in registry.get_all().items():
        _create_local_tool(mcp, plugin)


def _create_local_tool(mcp: FastMCP, plugin: BaseToolPlugin) -> None:
    """Create a single MCP tool function for a plugin."""

    # Build a rich description including parameters
    schema = plugin.InputSchema.model_json_schema()
    props = schema.get("properties", {})
    param_desc = "\n".join(
        f"    - {pname}: {pinfo.get('description', pinfo.get('type', 'string'))}"
        f"{' (default: ' + json.dumps(pinfo.get('default')) + ')' if 'default' in pinfo else ''}"
        for pname, pinfo in props.items()
    )

    doc = f"""{plugin.description}

Category: {plugin.category.value}
Required binaries: {', '.join(plugin.required_binaries) or 'none'}
Timeout: {plugin.timeout}s

Parameters:
{param_desc}
"""

    async def _execute(params_json: str) -> dict[str, Any]:
        """Execute the tool with the given JSON parameters string."""
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON parameters: {params_json}"}

        if not plugin.is_available():
            missing = plugin.get_missing_binaries()
            return {
                "error": f"Tool '{plugin.name}' is not installed",
                "missing_binaries": missing,
                "install_hint": f"Install with: sudo apt install {' '.join(missing)}",
            }

        result = await runner.run(plugin, params)

        # Save to database
        try:
            await save_result(result)
        except Exception as e:
            log.warning(f"Failed to persist result: {e}")

        return result.to_dict()

    # Dynamically set function name and docstring
    _execute.__name__ = f"run_{plugin.name.replace('-', '_')}"
    _execute.__doc__ = doc

    # Register with MCP
    mcp.tool()(_execute)
    log.debug(f"Registered MCP tool: run_{plugin.name}")


# ── Remote mode tool registration ─────────────────────────────────────────────

def _register_remote_tools(mcp: FastMCP, server_url: str) -> None:
    """
    Register MCP tools that delegate to a remote PhantomStrike API server.

    This is useful when the MCP client runs on a different machine
    (e.g., macOS host) than where the tools are installed (e.g., Kali VM).
    """
    for name, plugin in registry.get_all().items():
        _create_remote_tool(mcp, plugin, server_url)


def _create_remote_tool(mcp: FastMCP, plugin: BaseToolPlugin, server_url: str) -> None:
    """Create a remote MCP tool that forwards to the API server."""

    async def _execute(params_json: str) -> dict[str, Any]:
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON parameters: {params_json}"}

        async with httpx.AsyncClient(timeout=plugin.timeout + 30) as client:
            try:
                response = await client.post(
                    f"{server_url}/api/tools/execute",
                    json={"tool": plugin.name, "params": params, "timeout": plugin.timeout},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                return {"error": f"API request failed: {e}"}

    _execute.__name__ = f"run_{plugin.name.replace('-', '_')}"
    _execute.__doc__ = plugin.description

    mcp.tool()(_execute)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    """CLI entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="PhantomStrike MCP Server")
    parser.add_argument(
        "--mode", choices=["local", "remote"], default="local",
        help="Execution mode: local (direct) or remote (API delegation)",
    )
    parser.add_argument(
        "--server", default="http://127.0.0.1:8443",
        help="PhantomStrike API server URL (for remote mode)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    args = parser.parse_args()

    setup_logging(level=args.log_level)
    print_banner()

    # Initialize plugin registry
    registry.auto_discover()
    log.info(f"Mode: {args.mode} | Plugins: {len(registry)} | Available: {len(registry.get_available())}")

    if args.mode == "local":
        # Initialize database for local mode
        asyncio.get_event_loop().run_until_complete(init_db())

    mcp = create_mcp_server(mode=args.mode, server_url=args.server)

    log.info("MCP server ready — waiting for AI agent connection…")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
