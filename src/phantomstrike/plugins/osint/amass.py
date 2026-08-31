"""
Amass Plugin — Advanced subdomain enumeration and OSINT.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class AmassPlugin(BaseToolPlugin):
    name = "amass"
    category = ToolCategory.OSINT
    description = (
        "In-depth attack surface mapping and subdomain enumeration. Uses DNS, web scraping, "
        "certificate transparency, APIs, and search engines for comprehensive OSINT."
    )
    required_binaries = ["amass"]
    timeout = 600

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target domain (e.g. example.com)")
        mode: str = Field("enum", description="Mode: enum (enumerate), intel (intelligence)")
        passive: bool = Field(True, description="Passive only (no DNS resolution/brute force)")
        additional_args: str = Field("", description="Additional Amass arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["amass", params.mode, "-d", params.target]

        if params.passive:
            cmd.append("-passive")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    # Amass's own wording (checked against the real v4.1.0 binary) when
    # -passive is set: it deliberately prints no discovered names at all.
    _PASSIVE_NO_OUTPUT_MARKER = "Passive mode does not generate output during the enumeration"

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        subdomains = [line.strip() for line in stdout.strip().split("\n") if line.strip() and "." in line]

        for sub in subdomains:
            result.findings.append(Finding(
                title=f"Subdomain: {sub}", severity=Severity.INFO, target=sub,
            ))

        result.parsed_data = {"subdomains": subdomains, "total": len(subdomains)}

        if not subdomains and self._PASSIVE_NO_OUTPUT_MARKER in stderr:
            # Checked every documented flag on the real binary (-o, -oA, -v,
            # -json) — none of them make passive mode print names. Amass
            # stores them only in its local graph database in this mode.
            # "0 subdomains" here does NOT mean the domain has none; without
            # this note that's exactly what it looks like.
            result.parsed_data["note"] = (
                "Amass ran in passive mode, which stores discovered names in its local "
                "graph database instead of printing them — this is not a failure, and "
                "does not mean the domain has no subdomains. Retrieve them with a "
                "follow-up kali_shell command: amass db -names -d <target>. To get "
                "results directly from this tool instead, call it again with "
                "passive=false (enables DNS resolution against the target)."
            )
        elif exit_code != 0 and not subdomains:
            result.error_message = stderr or "Amass enumeration failed"
        return result
