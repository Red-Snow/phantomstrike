"""
Nmap Plugin — Advanced port scanning and service detection.

Nmap is the gold standard for network discovery. This plugin uses XML output (-oX -)
for reliable structured parsing instead of raw text.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class NmapPlugin(BaseToolPlugin):
    name = "nmap"
    category = ToolCategory.NETWORK
    description = (
        "Advanced port scanning and service detection using Nmap. "
        "Discovers open ports, running services, versions, and OS information. "
        "Supports NSE scripts for vulnerability detection."
    )
    required_binaries = ["nmap"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="IP address, hostname, CIDR range, or URL to scan")
        scan_type: str = Field("-sV", description="Scan type flags, e.g. -sV, -sS, -sC, -A")
        ports: str = Field("", description="Port specification, e.g. '22,80,443' or '1-1000' or empty for default")
        timing: int = Field(4, ge=0, le=5, description="Timing template T0-T5 (0=paranoid, 5=insane)")
        scripts: str = Field("", description="NSE scripts to run, e.g. 'vuln,safe' or 'http-*'")
        os_detection: bool = Field(False, description="Enable OS detection (-O)")
        additional_args: str = Field("", description="Additional Nmap arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["nmap"]

        # Output as XML for structured parsing
        cmd.extend(["-oX", "-"])

        # Scan type
        for flag in params.scan_type.split():
            cmd.append(flag)

        # Ports
        if params.ports:
            cmd.extend(["-p", params.ports])

        # Timing
        cmd.append(f"-T{params.timing}")

        # NSE scripts
        if params.scripts:
            cmd.extend(["--script", params.scripts])

        # OS detection
        if params.os_detection:
            cmd.append("-O")

        # Additional args (validated)
        if params.additional_args:
            cmd.extend(params.additional_args.split())

        # Target last
        cmd.append(params.target)

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="",
        )

        if exit_code != 0:
            result.error_message = stderr or "Nmap scan failed"
            result.stdout = stdout
            result.stderr = stderr
            return result

        # Parse XML output
        try:
            root = ET.fromstring(stdout)
        except ET.ParseError:
            # Fallback — return raw output if XML parsing fails
            result.stdout = stdout
            result.stderr = stderr
            result.parsed_data = {"raw_output": stdout}
            return result

        hosts = []
        for host_elem in root.findall(".//host"):
            host_data = {}

            # IP address
            addr = host_elem.find("address")
            if addr is not None:
                host_data["ip"] = addr.get("addr", "")
                result.target = host_data["ip"]

            # Hostname
            hostname = host_elem.find(".//hostname")
            if hostname is not None:
                host_data["hostname"] = hostname.get("name", "")

            # Status
            status = host_elem.find("status")
            if status is not None:
                host_data["state"] = status.get("state", "unknown")

            # Ports
            ports = []
            for port_elem in host_elem.findall(".//port"):
                port_info = {
                    "port": int(port_elem.get("portid", 0)),
                    "protocol": port_elem.get("protocol", "tcp"),
                }

                state = port_elem.find("state")
                if state is not None:
                    port_info["state"] = state.get("state", "unknown")

                service = port_elem.find("service")
                if service is not None:
                    port_info["service"] = service.get("name", "")
                    port_info["product"] = service.get("product", "")
                    port_info["version"] = service.get("version", "")
                    port_info["extra_info"] = service.get("extrainfo", "")

                # NSE script output
                scripts = []
                for script_elem in port_elem.findall("script"):
                    script_data = {
                        "id": script_elem.get("id", ""),
                        "output": script_elem.get("output", ""),
                    }
                    scripts.append(script_data)

                    # Generate findings from NSE vuln scripts
                    if "VULNERABLE" in script_data["output"].upper():
                        result.findings.append(Finding(
                            title=f"Vulnerability found by NSE: {script_data['id']}",
                            severity=Severity.HIGH,
                            description=script_data["output"][:500],
                            target=f"{host_data.get('ip', '')}:{port_info['port']}",
                            evidence=script_data["output"],
                        ))

                if scripts:
                    port_info["scripts"] = scripts

                ports.append(port_info)

                # Create info finding for open ports with services
                if port_info.get("state") == "open":
                    svc = port_info.get("service", "unknown")
                    ver = port_info.get("version", "")
                    result.findings.append(Finding(
                        title=f"Open port {port_info['port']}/{port_info['protocol']}: {svc} {ver}".strip(),
                        severity=Severity.INFO,
                        target=host_data.get("ip", ""),
                        description=f"Service: {svc}, Product: {port_info.get('product', '')}, Version: {ver}",
                    ))

            host_data["ports"] = ports

            # OS detection
            os_matches = []
            for os_match in host_elem.findall(".//osmatch"):
                os_matches.append({
                    "name": os_match.get("name", ""),
                    "accuracy": os_match.get("accuracy", ""),
                })
            if os_matches:
                host_data["os_matches"] = os_matches

            hosts.append(host_data)

        # Scan stats
        run_stats = root.find(".//runstats/finished")
        stats = {}
        if run_stats is not None:
            stats["elapsed"] = run_stats.get("elapsed", "")
            stats["summary"] = run_stats.get("summary", "")

        hosts_stat = root.find(".//runstats/hosts")
        if hosts_stat is not None:
            stats["hosts_up"] = hosts_stat.get("up", "0")
            stats["hosts_down"] = hosts_stat.get("down", "0")
            stats["hosts_total"] = hosts_stat.get("total", "0")

        result.parsed_data = {
            "hosts": hosts,
            "stats": stats,
        }
        result.stdout = stdout
        result.stderr = stderr

        return result
