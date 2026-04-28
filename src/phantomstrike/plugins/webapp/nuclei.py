"""
Nuclei Plugin — Fast vulnerability scanner with 10,000+ templates.
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field

from phantomstrike.plugins.base import (
    BaseToolPlugin, Finding, Severity, ToolCategory, ToolResult, ToolStatus,
)

SEVERITY_MAP = {
    "critical": Severity.CRITICAL,
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "info": Severity.INFO,
}


class NucleiPlugin(BaseToolPlugin):
    name = "nuclei"
    category = ToolCategory.WEBAPP
    description = (
        "Fast and customizable vulnerability scanner based on community-maintained templates. "
        "Supports 10,000+ templates covering CVEs, misconfigurations, exposed panels, and more."
    )
    required_binaries = ["nuclei"]
    timeout = 600

    class InputSchema(BaseModel):
        target: str = Field(..., description="Target URL, IP, or file with list of targets")
        severity: str = Field("", description="Filter by severity: critical,high,medium,low,info")
        tags: str = Field("", description="Filter by tags: cve,rce,xss,sqli,lfi,ssrf,etc.")
        templates: str = Field("", description="Specific template path or ID")
        rate_limit: int = Field(150, description="Maximum requests per second")
        concurrency: int = Field(25, description="Number of concurrent templates")
        additional_args: str = Field("", description="Additional Nuclei arguments")

    def build_command(self, params: InputSchema) -> list[str]:
        cmd = ["nuclei", "-target", params.target]

        # JSON output for structured parsing
        cmd.extend(["-jsonl"])

        if params.severity:
            cmd.extend(["-severity", params.severity])

        if params.tags:
            cmd.extend(["-tags", params.tags])

        if params.templates:
            cmd.extend(["-t", params.templates])

        cmd.extend(["-rate-limit", str(params.rate_limit)])
        cmd.extend(["-concurrency", str(params.concurrency)])

        # Disable update check for faster execution
        cmd.append("-duc")

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

        # Parse JSONL output (one JSON object per line)
        vulnerabilities = []
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                vuln = json.loads(line)
                severity_str = vuln.get("info", {}).get("severity", "info").lower()
                severity = SEVERITY_MAP.get(severity_str, Severity.INFO)

                name = vuln.get("info", {}).get("name", "Unknown")
                matched = vuln.get("matched-at", "")
                template_id = vuln.get("template-id", "")
                description = vuln.get("info", {}).get("description", "")
                cve_ids = []

                # Extract CVE IDs from classification
                classification = vuln.get("info", {}).get("classification", {})
                if classification:
                    cve_ids = classification.get("cve-id", []) or []

                references = vuln.get("info", {}).get("reference", []) or []
                cvss_score = None
                if classification:
                    cvss_metrics = classification.get("cvss-metrics", "")
                    cvss_score_str = classification.get("cvss-score")
                    if cvss_score_str:
                        try:
                            cvss_score = float(cvss_score_str)
                        except (ValueError, TypeError):
                            pass

                finding = Finding(
                    title=f"[{template_id}] {name}",
                    severity=severity,
                    description=description[:500] if description else f"Detected by template: {template_id}",
                    target=matched,
                    evidence=vuln.get("matched-at", ""),
                    cve_ids=cve_ids if isinstance(cve_ids, list) else [cve_ids],
                    cvss_score=cvss_score,
                    references=references if isinstance(references, list) else [references],
                    remediation=vuln.get("info", {}).get("remediation", ""),
                )

                result.findings.append(finding)
                vulnerabilities.append({
                    "template_id": template_id,
                    "name": name,
                    "severity": severity_str,
                    "matched_at": matched,
                    "cve_ids": cve_ids,
                })

                if not result.target and matched:
                    result.target = matched

            except json.JSONDecodeError:
                continue

        result.parsed_data = {
            "vulnerabilities": vulnerabilities,
            "total_found": len(vulnerabilities),
            "by_severity": result.finding_counts,
        }

        if exit_code != 0 and not vulnerabilities:
            result.error_message = stderr or "Nuclei scan failed"

        return result
