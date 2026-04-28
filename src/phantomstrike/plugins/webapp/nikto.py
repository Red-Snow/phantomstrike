"""
Nikto Plugin — Web server vulnerability scanner.
"""

from __future__ import annotations

import json
import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class NiktoPlugin(BaseToolPlugin):
    name = "nikto"
    category = ToolCategory.WEBAPP
    description = (
        "Comprehensive web server scanner that tests for dangerous files, outdated software, "
        "version-specific problems, and server configuration issues."
    )
    required_binaries = ["nikto"]
    timeout = 600

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target URL or IP (e.g. http://example.com or 192.168.1.1)")
        port: int = Field(0, description="Target port (0 = auto-detect from URL)")
        tuning: str = Field("", description="Scan tuning: 1=files, 2=misconfig, 3=info, 4=XSS, 9=sqli")
        additional_args: str = Field("", description="Additional Nikto arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["nikto", "-h", params.target]

        # JSON output
        cmd.extend(["-Format", "json", "-output", "/dev/stdout"])

        if params.port:
            cmd.extend(["-p", str(params.port)])

        if params.tuning:
            cmd.extend(["-Tuning", params.tuning])

        # Disable interactive
        cmd.append("-nointeractive")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        vulnerabilities = []
        try:
            data = json.loads(stdout)
            for vuln in data.get("vulnerabilities", []):
                osvdb = vuln.get("OSVDB", "")
                msg = vuln.get("msg", "")
                url = vuln.get("url", "")
                method = vuln.get("method", "GET")

                severity = Severity.MEDIUM
                if any(kw in msg.lower() for kw in ["xss", "injection", "rce", "remote code"]):
                    severity = Severity.HIGH
                elif any(kw in msg.lower() for kw in ["information", "version", "header"]):
                    severity = Severity.LOW

                vulnerabilities.append({"osvdb": osvdb, "message": msg, "url": url, "method": method})
                result.findings.append(Finding(
                    title=f"[OSVDB-{osvdb}] {msg[:80]}",
                    severity=severity,
                    target=url,
                    description=msg,
                    evidence=f"Method: {method}, URL: {url}",
                ))
        except json.JSONDecodeError:
            # Fallback: parse text output
            for line in stdout.split("\n"):
                if "+ " in line and "OSVDB" in line:
                    result.findings.append(Finding(
                        title=line.strip()[:100],
                        severity=Severity.MEDIUM,
                        description=line.strip(),
                    ))

        result.parsed_data = {"vulnerabilities": vulnerabilities, "total": len(result.findings)}
        if exit_code != 0 and not result.findings:
            result.error_message = stderr or "Nikto scan failed"
        return result
