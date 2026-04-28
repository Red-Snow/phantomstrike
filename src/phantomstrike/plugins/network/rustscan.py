"""
Rustscan Plugin — Ultra-fast port scanning.

Rustscan scans all 65535 ports in seconds, then hands off to Nmap for service detection.
"""

from __future__ import annotations

import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class RustscanPlugin(BaseToolPlugin):
    name = "rustscan"
    category = ToolCategory.NETWORK
    description = (
        "Ultra-fast port scanner that discovers open ports in seconds. "
        "Scans all 65535 ports rapidly, then optionally passes results to Nmap for service detection."
    )
    required_binaries = ["rustscan"]
    timeout = 120

    class InputSchema(BaseModel):
        target: str = Field(..., description="IP address or hostname to scan")
        ports: str = Field("", description="Specific ports to scan (empty = all ports)")
        ulimit: int = Field(5000, description="File descriptor ulimit for concurrent connections")
        batch_size: int = Field(4500, description="Batch size for port scanning")
        timeout_ms: int = Field(1500, description="Connection timeout in milliseconds")
        scripts: bool = Field(False, description="Run Nmap scripts on discovered ports")
        additional_args: str = Field("", description="Additional Rustscan arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["rustscan", "-a", params.target]

        if params.ports:
            cmd.extend(["-p", params.ports])

        cmd.extend(["--ulimit", str(params.ulimit)])
        cmd.extend(["-b", str(params.batch_size)])
        cmd.extend(["-t", str(params.timeout_ms)])

        if params.scripts:
            cmd.append("--scripts")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="",
            stdout=stdout,
            stderr=stderr,
        )

        # Parse open ports from Rustscan output
        open_ports = []
        port_pattern = re.compile(r"Open\s+(\d+\.\d+\.\d+\.\d+):(\d+)")
        for match in port_pattern.finditer(stdout):
            ip = match.group(1)
            port = int(match.group(2))
            open_ports.append({"ip": ip, "port": port})
            result.target = ip

            result.findings.append(Finding(
                title=f"Open port {port} discovered",
                severity=Severity.INFO,
                target=f"{ip}:{port}",
            ))

        # Also try simpler format
        if not open_ports:
            simple_pattern = re.compile(r"(\d+)/(?:tcp|udp)\s+open")
            for match in simple_pattern.finditer(stdout):
                port = int(match.group(1))
                open_ports.append({"port": port})
                result.findings.append(Finding(
                    title=f"Open port {port} discovered",
                    severity=Severity.INFO,
                    target=result.target,
                ))

        result.parsed_data = {"open_ports": open_ports, "total_open": len(open_ports)}

        if exit_code != 0:
            result.error_message = stderr or "Rustscan failed"

        return result
