#!/usr/bin/env python3
"""
PhantomStrike Local Proxy Daemon

Bridges the gap between Claude Desktop's network-sandboxed MCP process
and the remote Kali VM API server.

Listens on a Unix domain socket and forwards HTTP requests to the remote server.
Run this independently (NOT from Claude Desktop).

Usage:
    python3 proxy_daemon.py --remote http://150.1.7.101:8443
"""

import argparse
import asyncio
import json
import os
import signal
import sys

import httpx

SOCKET_PATH = "/tmp/phantomstrike_proxy.sock"


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_url: str):
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

        async with httpx.AsyncClient(timeout=timeout + 30) as client:
            if method == "POST":
                resp = await client.post(url, json=body)
            else:
                resp = await client.get(url)

            response = {
                "status": resp.status_code,
                "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
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


async def main(remote_url: str):
    # Clean up stale socket
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = await asyncio.start_unix_server(
        lambda r, w: handle_client(r, w, remote_url),
        path=SOCKET_PATH,
    )
    os.chmod(SOCKET_PATH, 0o666)

    print(f"🔌 PhantomStrike Proxy Daemon running")
    print(f"   Socket: {SOCKET_PATH}")
    print(f"   Remote: {remote_url}")
    print(f"   Press Ctrl+C to stop")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PhantomStrike Local Proxy Daemon")
    parser.add_argument("--remote", default="http://150.1.7.101:8443", help="Remote Kali API URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.remote))
    except KeyboardInterrupt:
        print("\n🛑 Proxy daemon stopped.")
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
