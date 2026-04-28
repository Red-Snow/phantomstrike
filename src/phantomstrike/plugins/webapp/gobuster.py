"""
Gobuster Plugin — Directory, DNS, and vhost enumeration.
"""

from __future__ import annotations

import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class GobusterPlugin(BaseToolPlugin):
    name = "gobuster"
    category = ToolCategory.WEBAPP
    description = (
        "Directory/file enumeration tool using brute force. "
        "Discovers hidden directories, files, DNS subdomains, and virtual hosts."
    )
    required_binaries = ["gobuster"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target URL (e.g., http://example.com)")
        mode: str = Field("dir", description="Scan mode: dir, dns, vhost, fuzz")
        wordlist: str = Field(
            "/usr/share/wordlists/dirb/common.txt",
            description="Path to wordlist file"
        )
        extensions: str = Field("", description="File extensions to search, e.g. 'php,html,txt'")
        threads: int = Field(20, ge=1, le=100, description="Number of concurrent threads")
        status_codes: str = Field("200,204,301,302,307,401,403", description="Status codes to match")
        additional_args: str = Field("", description="Additional Gobuster arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["gobuster", params.mode]

        if params.mode in ("dir", "fuzz"):
            cmd.extend(["-u", params.target])
        elif params.mode == "dns":
            cmd.extend(["-d", params.target])
        elif params.mode == "vhost":
            cmd.extend(["-u", params.target])

        cmd.extend(["-w", params.wordlist])
        cmd.extend(["-t", str(params.threads)])

        if params.extensions and params.mode == "dir":
            cmd.extend(["-x", params.extensions])

        if params.status_codes and params.mode in ("dir", "fuzz"):
            cmd.extend(["-s", params.status_codes])

        # Quiet mode — no banner
        cmd.append("-q")

        # No color (easier to parse)
        cmd.append("--no-color")

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

        discovered = []
        # Parse dir mode output: /path (Status: 200) [Size: 1234]
        dir_pattern = re.compile(r"(/\S*)\s+\(Status:\s*(\d+)\)(?:\s+\[Size:\s*(\d+)\])?")
        for match in dir_pattern.finditer(stdout):
            path = match.group(1)
            status = int(match.group(2))
            size = match.group(3)

            entry = {"path": path, "status_code": status}
            if size:
                entry["size"] = int(size)
            discovered.append(entry)

            severity = Severity.INFO
            if status in (200, 204):
                severity = Severity.LOW
            elif status in (401, 403):
                severity = Severity.MEDIUM

            result.findings.append(Finding(
                title=f"Discovered: {path} (HTTP {status})",
                severity=severity,
                target=path,
                description=f"Directory/file found with status code {status}",
            ))

        # If dir pattern didn't match, try simpler line-by-line
        if not discovered:
            for line in stdout.strip().split("\n"):
                line = line.strip()
                if line and not line.startswith("=") and not line.startswith("["):
                    discovered.append({"path": line})
                    result.findings.append(Finding(
                        title=f"Discovered: {line}",
                        severity=Severity.INFO,
                        target=line,
                    ))

        result.parsed_data = {
            "discovered_paths": discovered,
            "total_discovered": len(discovered),
        }

        if exit_code != 0 and not discovered:
            result.error_message = stderr or "Gobuster scan failed"

        return result
