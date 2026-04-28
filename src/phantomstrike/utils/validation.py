"""
PhantomStrike Input Validation — prevent injection and enforce correctness.

Every tool parameter goes through validation before reaching subprocess.
"""

import re
import ipaddress
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator


# ── Regex patterns ────────────────────────────────────────────────────────────

DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$"
)

URL_RE = re.compile(
    r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$"
)

PORT_RE = re.compile(r"^\d{1,5}$")

PORT_RANGE_RE = re.compile(
    r"^(\d{1,5}(-\d{1,5})?(,\s*\d{1,5}(-\d{1,5})?)*)$"
)

# Characters that must NEVER appear in arguments passed to subprocess
SHELL_DANGEROUS_CHARS = re.compile(r"[;&|`$(){}!<>\n\r\\]")

# Allowed characters for wordlist / file paths
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_./ -]+$")


class ValidationError(Exception):
    """Raised when user input fails validation."""

    def __init__(self, field: str, value: str, reason: str):
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Validation failed for '{field}': {reason} (got: {value!r})")


# ── Validators ────────────────────────────────────────────────────────────────

def validate_target(target: str) -> str:
    """
    Validate a scan target — must be an IP, CIDR, domain, or URL.

    Raises ValidationError if the target looks suspicious.
    """
    target = target.strip()

    if not target:
        raise ValidationError("target", target, "Target cannot be empty")

    # Check for shell injection attempts
    if SHELL_DANGEROUS_CHARS.search(target):
        raise ValidationError("target", target, "Target contains dangerous characters")

    # Try IP address
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        pass

    # Try CIDR notation
    try:
        ipaddress.ip_network(target, strict=False)
        return target
    except ValueError:
        pass

    # Try URL
    if URL_RE.match(target):
        return target

    # Try domain
    if DOMAIN_RE.match(target):
        return target

    raise ValidationError(
        "target", target,
        "Must be a valid IP, CIDR range, domain, or URL"
    )


def validate_ports(ports: str) -> str:
    """Validate a port specification string like '80,443,8080-8090'."""
    ports = ports.strip()
    if not ports:
        return ports

    if not PORT_RANGE_RE.match(ports):
        raise ValidationError("ports", ports, "Invalid port format. Use: 80,443,8080-8090")

    # Verify each port number is in valid range
    for part in ports.split(","):
        part = part.strip()
        for p in part.split("-"):
            port_num = int(p.strip())
            if not 1 <= port_num <= 65535:
                raise ValidationError("ports", ports, f"Port {port_num} out of range (1-65535)")

    return ports


def validate_file_path(path: str, must_exist: bool = False) -> str:
    """
    Validate a file path — no traversal, no injection.

    Args:
        path: File path to validate.
        must_exist: If True, verify the file actually exists.
    """
    path = path.strip()
    if not path:
        return path

    # Block path traversal
    if ".." in path:
        raise ValidationError("path", path, "Path traversal (..) is not allowed")

    # Block shell-dangerous characters
    if not SAFE_PATH_RE.match(path):
        raise ValidationError("path", path, "Path contains disallowed characters")

    if must_exist and not Path(path).exists():
        raise ValidationError("path", path, "File does not exist")

    return path


def validate_additional_args(args: str) -> str:
    """
    Validate additional CLI arguments — block dangerous shell characters.

    This is the most critical validator. We allow flags/values but block
    shell metacharacters that could enable injection.
    """
    args = args.strip()
    if not args:
        return args

    # Block dangerous shell metacharacters
    if SHELL_DANGEROUS_CHARS.search(args):
        raise ValidationError(
            "additional_args", args,
            "Arguments contain dangerous shell characters (;, &, |, `, $, etc.)"
        )

    return args


def sanitize_for_display(text: str, max_length: int = 200) -> str:
    """Truncate and clean text for safe display in logs and UI."""
    text = text.replace("\x00", "")  # Remove null bytes
    if len(text) > max_length:
        return text[:max_length] + "…"
    return text
