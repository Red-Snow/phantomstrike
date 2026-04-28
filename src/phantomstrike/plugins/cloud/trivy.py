"""
Trivy Plugin — Container and filesystem vulnerability scanner.
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)

SEVERITY_MAP = {"CRITICAL": Severity.CRITICAL, "HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW, "UNKNOWN": Severity.INFO}


class TrivyPlugin(BaseToolPlugin):
    name = "trivy"
    category = ToolCategory.CLOUD
    description = (
        "Comprehensive vulnerability scanner for containers, filesystems, Git repos, and IaC. "
        "Detects vulnerabilities (CVEs), misconfigurations, secrets, and license issues."
    )
    required_binaries = ["trivy"]
    timeout = 300

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target: container image, directory, or Git repo URL")
        scan_type: str = Field("image", description="Scan type: image, fs, repo, config, sbom")
        severity: str = Field("HIGH,CRITICAL", description="Severity filter: UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL")
        additional_args: str = Field("", description="Additional Trivy arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["trivy", params.scan_type, "--format", "json"]

        if params.severity:
            cmd.extend(["--severity", params.severity])

        if params.additional_args:
            cmd.extend(params.additional_args.split())

        cmd.append(params.target)
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        result = ToolResult(
            tool_name=self.name, status=ToolStatus.SUCCESS if exit_code == 0 else ToolStatus.FAILED,
            target="", stdout=stdout, stderr=stderr,
        )

        all_vulns = []
        try:
            data = json.loads(stdout)
            for target_result in data.get("Results", []):
                target_name = target_result.get("Target", "")
                for vuln in target_result.get("Vulnerabilities", []) or []:
                    vuln_id = vuln.get("VulnerabilityID", "")
                    severity_str = vuln.get("Severity", "UNKNOWN")
                    pkg = vuln.get("PkgName", "")
                    installed = vuln.get("InstalledVersion", "")
                    fixed = vuln.get("FixedVersion", "")
                    title = vuln.get("Title", vuln_id)

                    all_vulns.append({
                        "id": vuln_id, "severity": severity_str, "package": pkg,
                        "installed": installed, "fixed": fixed, "target": target_name,
                    })

                    result.findings.append(Finding(
                        title=f"[{vuln_id}] {title}",
                        severity=SEVERITY_MAP.get(severity_str, Severity.INFO),
                        target=target_name,
                        description=f"Package: {pkg} {installed} → Fix: {fixed or 'N/A'}",
                        cve_ids=[vuln_id] if vuln_id.startswith("CVE-") else [],
                        remediation=f"Update {pkg} to version {fixed}" if fixed else "No fix available",
                    ))
        except json.JSONDecodeError:
            result.parsed_data = {"raw_output": stdout}

        result.parsed_data = {"vulnerabilities": all_vulns, "total": len(all_vulns)}
        if exit_code != 0 and not all_vulns:
            result.error_message = stderr or "Trivy scan failed"
        return result
