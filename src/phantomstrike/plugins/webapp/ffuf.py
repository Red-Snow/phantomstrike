"""
FFuf Plugin — Fast web fuzzer for directory, parameter, and vhost discovery.
"""

from __future__ import annotations

import re
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

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        return cmd

    # Matches ffuf's default per-result line, e.g.:
    #   docs   [Status: 200, Size: 81, Words: 1, Lines: 1, Duration: 3ms]
    _RESULT_PATTERN = re.compile(
        r"(\S+)\s+\[Status:\s*(\d+),\s*Size:\s*(\d+),\s*Words:\s*(\d+),\s*Lines:\s*(\d+)"
    )
    # ffuf redraws its progress line in place using ANSI cursor-control
    # codes (e.g. "\x1b[2K" to clear the line). Confirmed against the real
    # binary: those codes land immediately before the matched value with no
    # separating whitespace, so a plain \S+ match for the first group
    # swallows them into the reported name unless stripped first.
    _ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        # ffuf previously wrote JSON to "-o /dev/stdout", but opening that path
        # as a second file handle while stdout is already a pipe (which is how
        # the runner always invokes it) reliably fails with
        # "open /dev/stdout: no such device or address" on this environment,
        # silently dropping every result. Parsing ffuf's normal result lines
        # (always printed regardless of -o) avoids the failure mode entirely —
        # confirmed against the real ffuf 2.1.0-dev binary.
        clean_stdout = self._ANSI_ESCAPE.sub("", stdout)

        discovered = []
        for match in self._RESULT_PATTERN.finditer(clean_stdout):
            fuzz_value, status, size, words, lines = match.groups()
            item = {
                "input": fuzz_value,
                "status": int(status),
                "length": int(size),
                "words": int(words),
                "lines": int(lines),
            }
            discovered.append(item)
            result.findings.append(Finding(
                title=f"Discovered: {item['input']} (HTTP {item['status']})",
                severity=Severity.LOW if item["status"] in (200, 204) else Severity.INFO,
                target=item["input"],
                description=f"Size: {item['length']} bytes, Words: {item['words']}",
            ))

        result.parsed_data = {"discovered": discovered, "total": len(discovered)}
        if exit_code != 0 and not discovered:
            result.error_message = stderr or "FFuf scan failed"
        return result
