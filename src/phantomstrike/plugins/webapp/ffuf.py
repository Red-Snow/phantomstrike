"""
FFuf Plugin — Fast web fuzzer for directory, parameter, and vhost discovery.
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class FfufPlugin(BaseToolPlugin):
    name = "ffuf"
    category = ToolCategory.WEBAPP
    description = (
        "Fast web fuzzer written in Go. Discovers directories, files, parameters, "
        "and virtual hosts through brute-force fuzzing with advanced filtering."
    )
    required_binaries = ["ffuf"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target URL with FUZZ keyword, e.g. 'http://example.com/FUZZ'")
        wordlist: str = Field("/usr/share/wordlists/dirb/common.txt", description="Path to wordlist")
        method: str = Field("GET", description="HTTP method (GET, POST, PUT)")
        match_codes: str = Field("200,204,301,302,307,401,403", description="HTTP status codes to match")
        filter_size: str = Field("", description="Filter response by size")
        threads: int = Field(40, ge=1, le=200, description="Number of concurrent threads")
        additional_args: str = Field("", description="Additional FFuf arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["ffuf", "-u", params.target, "-w", params.wordlist]

        cmd.extend(["-X", params.method])
        cmd.extend(["-mc", params.match_codes])
        cmd.extend(["-t", str(params.threads)])

        if params.filter_size:
            cmd.extend(["-fs", params.filter_size])

        # JSON output
        cmd.extend(["-of", "json", "-o", "/dev/stdout"])

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        discovered = []
        try:
            data = json.loads(stdout)
            for entry in data.get("results", []):
                item = {
                    "input": entry.get("input", {}).get("FUZZ", ""),
                    "url": entry.get("url", ""),
                    "status": entry.get("status", 0),
                    "length": entry.get("length", 0),
                    "words": entry.get("words", 0),
                    "lines": entry.get("lines", 0),
                }
                discovered.append(item)
                result.findings.append(Finding(
                    title=f"Discovered: {item['input']} (HTTP {item['status']})",
                    severity=Severity.LOW if item["status"] in (200, 204) else Severity.INFO,
                    target=item["url"],
                    description=f"Size: {item['length']} bytes, Words: {item['words']}",
                ))
        except json.JSONDecodeError:
            result.parsed_data = {"raw_output": stdout}

        result.parsed_data = {"discovered": discovered, "total": len(discovered)}
        if exit_code != 0 and not discovered:
            result.error_message = stderr or "FFuf scan failed"
        return result
