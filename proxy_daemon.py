#!/usr/bin/env python3
"""
PhantomStrike Local Proxy Daemon

Bridges the gap between Claude Desktop's network-sandboxed MCP process and the
PhantomStrike API server (on a Kali VM, in Docker, or on localhost).

Claude Desktop runs MCP processes with outbound TCP blocked, including to
localhost. This daemon listens on a Unix domain socket — which the sandbox does
permit — and forwards each request over HTTP. Run it yourself in a terminal, not
from Claude Desktop.

Authentication
--------------
The API server requires an API key. This daemon holds it and attaches it to
every forwarded request, so the key stays out of your MCP client's config file.

    export PHANTOMSTRIKE_API_KEY="<the key the server was started with>"
    python3 proxy_daemon.py --remote http://192.168.72.128:8443

Usage:
    python3 proxy_daemon.py --remote http://<host>:8443
"""

import argparse
import asyncio
import json
import os
import sys

import httpx

SOCKET_PATH = "/tmp/phantomstrike_proxy.sock"
API_KEY_HEADER = "X-API-Key"


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    remote_url: str,
    api_key: str,
):
    """Handle a single request from the MCP client."""
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=30)
        if not data:
            writer.close()
            return

        request = json.loads(data.decode().strip())
        method = request.get("method", "GET")
        path = request.get("path", "/health")
        body = request.get("body")
        timeout = request.get("timeout", 600)

        url = f"{remote_url}{path}"

        # The API server authenticates every request that executes tools.
        # Attaching the key here keeps it out of the MCP client's config file.
        headers = {API_KEY_HEADER: api_key} if api_key else {}

        async with httpx.AsyncClient(timeout=timeout + 30) as client:
            if method == "POST":
                resp = await client.post(url, json=body, headers=headers)
            else:
                resp = await client.get(url, headers=headers)

            if resp.status_code == 401:
                # Say what to do about it. A bare 401 reaching the agent is
                # indistinguishable from the tool itself failing.
                response = {
                    "status": 401,
                    "error": (
                        "PhantomStrike API rejected the API key. Set "
                        "PHANTOMSTRIKE_API_KEY to the same value the server was "
                        "started with (PHANTOMSTRIKE_API_KEYS), then restart this "
                        "daemon."
                    ),
                }
            else:
                response = {
                    "status": resp.status_code,
                    "body": (
                        resp.json()
                        if resp.headers.get("content-type", "").startswith("application/json")
                        else resp.text
                    ),
                }

    except httpx.HTTPError as e:
        response = {"status": 502, "error": f"Proxy HTTP error: {e}"}
    except asyncio.TimeoutError:
        response = {"status": 504, "error": "Proxy timeout"}
    except Exception as e:
        response = {"status": 500, "error": f"Proxy error: {type(e).__name__}: {e}"}

    writer.write((json.dumps(response) + "\n").encode())
    await writer.drain()
    writer.close()


async def main(remote_url: str, api_key: str):
    # Clean up stale socket
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = await asyncio.start_unix_server(
        lambda r, w: handle_client(r, w, remote_url, api_key),
        path=SOCKET_PATH,
    )
    # Owner-only. At 0o666 any local account on a shared host could send
    # requests through this proxy to an API that executes commands.
    os.chmod(SOCKET_PATH, 0o600)

    print("🔌 PhantomStrike Proxy Daemon running")
    print(f"   Socket: {SOCKET_PATH}")
    print(f"   Remote: {remote_url}")
    print(f"   Auth:   {'API key loaded' if api_key else 'NO KEY SET'}")
    if not api_key:
        print()
        print("   ⚠️  No API key configured. The server requires one, so every")
        print("      tool call will fail with 401. Set it and restart:")
        print('         export PHANTOMSTRIKE_API_KEY="<your key>"')
    print("   Press Ctrl+C to stop")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PhantomStrike Local Proxy Daemon")
    parser.add_argument(
        "--remote",
        required=True,
        help="PhantomStrike API server URL, e.g. http://192.168.72.128:8443",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("PHANTOMSTRIKE_API_KEY", ""),
        help=(
            "API key for the server. Prefer the PHANTOMSTRIKE_API_KEY environment "
            "variable — a key passed as an argument is visible in shell history "
            "and to anyone running `ps`."
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.remote, args.api_key))
    except KeyboardInterrupt:
        print("\n🛑 Proxy daemon stopped.")
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
