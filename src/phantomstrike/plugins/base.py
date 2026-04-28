"""
PhantomStrike Plugin Base — the contract every tool plugin must implement.

This is the core abstraction that makes the entire framework extensible.
Adding a new security tool means creating ONE file that subclasses BaseToolPlugin.
"""

from __future__ import annotations

import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


# ── Enums ─────────────────────────────────────────────────────────────────────

class ToolCategory(str, Enum):
    """Categories for organizing tools in the registry and UI."""
    NETWORK = "network"
    WEBAPP = "webapp"
    CLOUD = "cloud"
    OSINT = "osint"
    PASSWORD = "password"
    BINARY = "binary"
    FORENSICS = "forensics"
    WIRELESS = "wireless"


class Severity(str, Enum):
    """Vulnerability severity levels (aligned with CVSS)."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ToolStatus(str, Enum):
    """Execution lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """A single vulnerability or interesting finding from a tool."""
    title: str
    severity: Severity
    description: str = ""
    target: str = ""
    evidence: str = ""
    remediation: str = ""
    cve_ids: list[str] = field(default_factory=list)
    cvss_score: Optional[float] = None
    references: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "severity": self.severity.value,
            "description": self.description,
            "target": self.target,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "cve_ids": self.cve_ids,
            "cvss_score": self.cvss_score,
            "references": self.references,
        }


@dataclass
class ToolResult:
    """
    Structured output from a tool execution.

    Every plugin must return this, ensuring consistent data for the AI agent,
    the report generator, and the database.
    """
    tool_name: str
    status: ToolStatus
    target: str
    command_executed: str = ""

    # Parsed data
    findings: list[Finding] = field(default_factory=list)
    parsed_data: dict[str, Any] = field(default_factory=dict)

    # Raw output (kept for debugging / AI analysis)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1

    # Metadata
    duration_seconds: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    error_message: str = ""

    @property
    def success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    @property
    def finding_counts(self) -> dict[str, int]:
        """Count findings by severity."""
        counts: dict[str, int] = {}
        for f in self.findings:
            key = f.severity.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "success": self.success,
            "target": self.target,
            "command_executed": self.command_executed,
            "findings": [f.to_dict() for f in self.findings],
            "finding_counts": self.finding_counts,
            "parsed_data": self.parsed_data,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }


# ── Base Plugin ───────────────────────────────────────────────────────────────

class BaseToolPlugin(ABC):
    """
    Abstract base class for all PhantomStrike tool plugins.

    To add a new tool, create a subclass and implement:
    - name, category, description, required_binaries (class attributes)
    - InputSchema (Pydantic model defining accepted parameters)
    - build_command() — turn validated params into a subprocess command list
    - parse_output() — turn raw stdout/stderr into a structured ToolResult
    """

    # ── Class-level metadata (override in subclass) ───────────────────────────

    name: str = ""
    """Unique tool identifier, e.g. 'nmap'."""

    category: ToolCategory = ToolCategory.NETWORK
    """Tool category for grouping."""

    description: str = ""
    """Human-readable description shown in MCP tool listing."""

    required_binaries: list[str] = []
    """System binaries that must be on $PATH for this tool to work."""

    version: str = "1.0.0"
    """Plugin version."""

    timeout: int = 600
    """Default timeout in seconds for this tool."""

    use_shell: bool = False
    """If True, command is executed in a shell (supports pipes and redirects)."""

    # ── Input schema (override in subclass) ───────────────────────────────────

    class InputSchema(BaseModel):
        """Default input schema — subclasses define their own."""
        target: str

    # ── Abstract methods ──────────────────────────────────────────────────────

    @abstractmethod
    def build_command(self, params: BaseModel) -> list[str]:
        """
        Build the subprocess command list from validated parameters.

        Args:
            params: Validated InputSchema instance.

        Returns:
            Command list like ["nmap", "-sV", "-p", "80,443", "example.com"].
        """
        ...

    @abstractmethod
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ToolResult:
        """
        Parse raw tool output into structured ToolResult.

        Args:
            stdout: Standard output from the tool.
            stderr: Standard error from the tool.
            exit_code: Process exit code.

        Returns:
            ToolResult with parsed findings and data.
        """
        ...

    # ── Concrete methods ──────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if all required binaries are installed."""
        return all(shutil.which(binary) is not None for binary in self.required_binaries)

    def get_missing_binaries(self) -> list[str]:
        """Return list of binaries that are not installed."""
        return [b for b in self.required_binaries if shutil.which(b) is None]

    def get_metadata(self) -> dict[str, Any]:
        """Return plugin metadata for registry and MCP tool listing."""
        return {
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "version": self.version,
            "required_binaries": self.required_binaries,
            "available": self.is_available(),
            "missing_binaries": self.get_missing_binaries(),
            "timeout": self.timeout,
            "input_schema": self.InputSchema.model_json_schema(),
        }

    def __repr__(self) -> str:
        status = "✅" if self.is_available() else "❌"
        return f"<Plugin {self.name} [{self.category.value}] {status}>"
