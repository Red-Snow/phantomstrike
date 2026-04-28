"""
SQLMap Plugin — Automatic SQL injection detection and exploitation.
"""

from __future__ import annotations

import re
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)


class SqlmapPlugin(BaseToolPlugin):
    name = "sqlmap"
    category = ToolCategory.WEBAPP
    description = (
        "Automatic SQL injection detection and exploitation tool. "
        "Detects and exploits SQL injection flaws in web applications. "
        "Supports multiple database backends (MySQL, PostgreSQL, MSSQL, Oracle, SQLite)."
    )
    required_binaries = ["sqlmap"]
    timeout = 600

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target URL with parameter, e.g. 'http://example.com/page?id=1'")
        data: str = Field("", description="POST data string for testing POST parameters")
        level: int = Field(1, ge=1, le=5, description="Test level (1-5, higher = more tests)")
        risk: int = Field(1, ge=1, le=3, description="Risk level (1-3, higher = riskier tests)")
        dbms: str = Field("", description="Force specific DBMS: mysql, postgresql, mssql, oracle, sqlite")
        technique: str = Field("", description="SQL injection techniques: B,E,U,S,T,Q")
        tamper: str = Field("", description="Tamper scripts: space2comment, randomcase, etc.")
        additional_args: str = Field("", description="Additional SQLMap arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["sqlmap", "-u", params.target]

        # Always batch mode (non-interactive)
        cmd.append("--batch")

        if params.data:
            cmd.extend(["--data", params.data])

        cmd.extend(["--level", str(params.level)])
        cmd.extend(["--risk", str(params.risk)])

        if params.dbms:
            cmd.extend(["--dbms", params.dbms])

        if params.technique:
            cmd.extend(["--technique", params.technique])

        if params.tamper:
            cmd.extend(["--tamper", params.tamper])

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

        # Detect SQL injection findings
        injectable_params = []
        injection_types = []

        # Find injectable parameters
        param_pattern = re.compile(r"Parameter:\s*['\"]?(\S+?)['\"]?\s+\((.*?)\)")
        for match in param_pattern.finditer(stdout):
            param_name = match.group(1)
            injection_type = match.group(2)
            injectable_params.append({"parameter": param_name, "type": injection_type})

        # Find injection types
        type_pattern = re.compile(r"Type:\s*(.*?)(?:\n|$)")
        for match in type_pattern.finditer(stdout):
            injection_types.append(match.group(1).strip())

        # Detect DBMS
        dbms_match = re.search(r"back-end DBMS:\s*(.*?)(?:\n|$)", stdout)
        dbms = dbms_match.group(1).strip() if dbms_match else ""

        # Check if vulnerable
        is_vulnerable = "is vulnerable" in stdout.lower() or len(injectable_params) > 0

        if is_vulnerable:
            for param in injectable_params:
                result.findings.append(Finding(
                    title=f"SQL Injection: parameter '{param['parameter']}' is injectable",
                    severity=Severity.CRITICAL,
                    description=f"Injection type: {param['type']}. DBMS: {dbms}",
                    target=result.target,
                    evidence=f"Parameter: {param['parameter']}, Type: {param['type']}",
                    remediation="Use parameterized queries/prepared statements. Never concatenate user input into SQL queries.",
                ))

            if not injectable_params:
                result.findings.append(Finding(
                    title="SQL Injection vulnerability detected",
                    severity=Severity.CRITICAL,
                    description=f"SQLMap confirmed SQL injection. DBMS: {dbms}",
                    remediation="Use parameterized queries/prepared statements.",
                ))

        result.parsed_data = {
            "vulnerable": is_vulnerable,
            "injectable_parameters": injectable_params,
            "injection_types": injection_types,
            "dbms": dbms,
        }

        if exit_code != 0 and not is_vulnerable:
            result.error_message = stderr or "SQLMap scan failed"

        return result
