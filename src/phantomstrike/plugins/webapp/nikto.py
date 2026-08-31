"""
Nikto Plugin — Web server vulnerability scanner.
"""

from __future__ import annotations

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

        # No -Format/-output here: "-Format json -output /dev/stdout" fails
        # outright, because Nikto appends a ".json" suffix to whatever path
        # follows -output when the format is json, turning it into
        # "/dev/stdout.json" — not a real device, so the write errors and the
        # whole scan exits non-zero (confirmed against the real 2.6.0
        # binary). Nikto's default plain-text report already goes to stdout
        # on its own; parse_output below reads that instead.
        if params.port:
            cmd.extend(["-p", str(params.port)])

        if params.tuning:
            cmd.extend(["-Tuning", params.tuning])

        # Disable interactive
        cmd.append("-nointeractive")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    # Lines that are scan bookkeeping, not a finding about the target.
    _METADATA_PREFIXES = (
        "+ Target IP:", "+ Target Hostname:", "+ Target Port:",
        "+ Start Time:", "+ End Time:",
    )
    # e.g. "+ 6544 items checked: 4 error(s) and 2 item(s) reported ..."
    # and  "+ 1 host(s) tested"
    _SUMMARY_LINE = re.compile(r"^\+\s*\d+\s+(items?\s+checked|host\(s\)\s+tested)", re.IGNORECASE)

    # Word-boundary matches only. A plain "kw in text" substring check (the
    # previous approach) misfires on ordinary text — e.g. "rce" matched
    # inside "force check" — confirmed while testing this fix live, so every
    # keyword here goes through \b...\b instead.
    _HIGH_SEVERITY_RE = re.compile(r"\b(xss|injection|rce|remote code)\b", re.IGNORECASE)
    _LOW_SEVERITY_RE = re.compile(r"\b(information|version|header|outdated|banner)\b", re.IGNORECASE)

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        # Nikto's plain-text report (what build_command now leaves as the
        # default) is a series of "+ <message>" lines. Modern Nikto (2.6.0,
        # confirmed live) rarely tags findings with "OSVDB-####" anymore —
        # that database was retired in 2016 — so a filter that required
        # "OSVDB" in the line, as this used to, silently dropped every real
        # finding a current install reports.
        vulnerabilities = []
        for raw_line in stdout.split("\n"):
            line = raw_line.strip()
            if not line.startswith("+ "):
                continue
            if line.startswith(self._METADATA_PREFIXES) or self._SUMMARY_LINE.match(line):
                continue

            msg = line[2:].strip()
            osvdb_match = re.search(r"OSVDB-(\d+)", line)
            osvdb = osvdb_match.group(1) if osvdb_match else ""

            severity = Severity.MEDIUM
            if self._HIGH_SEVERITY_RE.search(msg):
                severity = Severity.HIGH
            elif self._LOW_SEVERITY_RE.search(msg):
                severity = Severity.LOW

            vulnerabilities.append({"osvdb": osvdb, "message": msg, "url": "", "method": "GET"})
            result.findings.append(Finding(
                title=f"[OSVDB-{osvdb}] {msg[:80]}" if osvdb else msg[:100],
                severity=severity,
                description=msg,
            ))

        result.parsed_data = {"vulnerabilities": vulnerabilities, "total": len(result.findings)}
        if exit_code != 0 and not result.findings:
            result.error_message = stderr or "Nikto scan failed"
        return result
