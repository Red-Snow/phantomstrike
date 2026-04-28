"""
Subfinder Plugin — Passive subdomain enumeration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class SubfinderPlugin(BaseToolPlugin):
    name = "subfinder"
    category = ToolCategory.OSINT
    description = (
        "Fast passive subdomain enumeration tool that uses multiple online data sources "
        "including certificate transparency, search engines, and DNS datasets."
    )
    required_binaries = ["subfinder"]
    timeout = 180

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target domain (e.g. example.com)")
        all_sources: bool = Field(False, description="Use all available sources")
        recursive: bool = Field(False, description="Enable recursive subdomain enumeration")
        additional_args: str = Field("", description="Additional Subfinder arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["subfinder", "-d", params.target, "-silent"]

        if params.all_sources:
            cmd.append("-all")

        if params.recursive:
            cmd.append("-recursive")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        subdomains = [line.strip() for line in stdout.strip().split("\n") if line.strip()]

        for sub in subdomains:
            result.findings.append(Finding(
                title=f"Subdomain: {sub}", severity=Severity.INFO, target=sub,
            ))

        result.parsed_data = {"subdomains": subdomains, "total": len(subdomains)}
        if exit_code != 0 and not subdomains:
            result.error_message = stderr or "Subfinder failed"
        return result
