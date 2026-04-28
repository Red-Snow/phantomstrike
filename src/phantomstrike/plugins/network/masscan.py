"""
Masscan Plugin — High-speed Internet-scale port scanning.
"""

from __future__ import annotations

import json
import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class MasscanPlugin(BaseToolPlugin):
    name = "masscan"
    category = ToolCategory.NETWORK
    description = (
        "High-speed Internet-scale port scanner. Scans large IP ranges at millions of "
        "packets per second with configurable rate limiting and banner grabbing."
    )
    required_binaries = ["masscan"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target IP, CIDR range, or host")
        ports: str = Field("1-65535", description="Port range to scan")
        rate: int = Field(1000, description="Packets per second rate")
        banners: bool = Field(False, description="Enable banner grabbing for service detection")
        additional_args: str = Field("", description="Additional Masscan arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["masscan", params.target]
        cmd.extend(["-p", params.ports])
        cmd.extend(["--rate", str(params.rate)])

        # JSON output for parsing
        cmd.extend(["-oJ", "-"])

        if params.banners:
            cmd.append("--banners")

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

        # Parse JSON output
        open_ports = []
        try:
            # Masscan JSON output can be incomplete, try to fix common issues
            cleaned = stdout.strip()
            if cleaned.endswith(","):
                cleaned = cleaned[:-1]
            if not cleaned.endswith("]"):
                cleaned += "]"
            if not cleaned.startswith("["):
                cleaned = "[" + cleaned

            data = json.loads(cleaned)
            for entry in data:
                ip = entry.get("ip", "")
                for port_info in entry.get("ports", []):
                    port = port_info.get("port", 0)
                    proto = port_info.get("proto", "tcp")
                    status = port_info.get("status", "open")
                    service = port_info.get("service", {})

                    open_ports.append({
                        "ip": ip, "port": port, "protocol": proto,
                        "status": status, "banner": service.get("banner", ""),
                    })

                    if not result.target:
                        result.target = ip

                    result.findings.append(Finding(
                        title=f"Open port {port}/{proto} on {ip}",
                        severity=Severity.INFO,
                        target=f"{ip}:{port}",
                        evidence=service.get("banner", ""),
                    ))
        except (json.JSONDecodeError, TypeError):
            result.parsed_data = {"raw_output": stdout}

        result.parsed_data = {"open_ports": open_ports, "total_open": len(open_ports)}

        if exit_code != 0:
            result.error_message = stderr or "Masscan failed"

        return result
