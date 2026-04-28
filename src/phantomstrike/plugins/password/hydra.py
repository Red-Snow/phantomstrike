"""
Hydra Plugin — Network login brute-force tool.
"""

from __future__ import annotations

import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class HydraPlugin(BaseToolPlugin):
    name = "hydra"
    category = ToolCategory.PASSWORD
    description = (
        "Fast network logon cracker supporting 50+ protocols including SSH, FTP, HTTP, "
        "SMB, RDP, MySQL, PostgreSQL, VNC, and many more."
    )
    required_binaries = ["hydra"]
    timeout = 900

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target IP or hostname")
        service: str = Field("ssh", description="Service to attack: ssh, ftp, http-get, smb, rdp, mysql, etc.")
        username: str = Field("", description="Single username to test")
        username_file: str = Field("", description="File containing usernames")
        password: str = Field("", description="Single password to test")
        password_file: str = Field("", description="File containing passwords (e.g. /usr/share/wordlists/rockyou.txt)")
        port: int = Field(0, description="Target port (0 = default for service)")
        threads: int = Field(4, ge=1, le=64, description="Number of parallel connections")
        additional_args: str = Field("", description="Additional Hydra arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["hydra"]

        # Username
        if params.username:
            cmd.extend(["-l", params.username])
        elif params.username_file:
            cmd.extend(["-L", params.username_file])

        # Password
        if params.password:
            cmd.extend(["-p", params.password])
        elif params.password_file:
            cmd.extend(["-P", params.password_file])

        # Threads
        cmd.extend(["-t", str(params.threads)])

        # Port
        if params.port:
            cmd.extend(["-s", str(params.port)])

        # Verbose
        cmd.append("-V")

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        # Target and service last
        cmd.extend([params.target, params.service])

        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        # Parse found credentials
        credentials = []
        cred_pattern = re.compile(r"\[(\d+)\]\[(\S+)\]\s+host:\s+(\S+)\s+login:\s+(\S+)\s+password:\s+(\S+)")
        for match in cred_pattern.finditer(stdout):
            port = match.group(1)
            service = match.group(2)
            host = match.group(3)
            username = match.group(4)
            password = match.group(5)

            credentials.append({
                "host": host, "port": port, "service": service,
                "username": username, "password": password,
            })
            result.target = host

            result.findings.append(Finding(
                title=f"Valid credentials: {username}:{password} on {service}://{host}:{port}",
                severity=Severity.CRITICAL,
                target=f"{host}:{port}",
                description=f"Hydra found valid login credentials for {service} service",
                evidence=f"Username: {username}, Password: {password}",
                remediation="Change the password immediately. Enforce strong password policies. Consider implementing account lockout and MFA.",
            ))

        result.parsed_data = {"credentials_found": credentials, "total": len(credentials)}
        if exit_code != 0 and not credentials:
            result.error_message = stderr or "Hydra attack failed"
        return result
