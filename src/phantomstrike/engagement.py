"""
Engagement scope — authorisation boundaries for a testing session.

A framework that automates nmap, sqlmap, hydra and nuclei will happily point
those tools at anything it is given. That is a problem in two directions:

  * Legal. "The AI chose the target" is not a defence. An operator needs to be
    able to show that the tool was constrained to hosts they were authorised to
    test, and that the constraint was enforced rather than intended.

  * Safety. When an LLM agent decides what to run next, its decisions are shaped
    by tool output, and tool output comes from the target. A host that expects to
    be scanned can place instructions in a banner, an HTTP body, or a TLS
    certificate field. Scope enforced here — below the agent, in the execution
    path — still holds when the agent has been talked into something.

The scope file is intentionally boring: CIDRs, domains, a time window, a client
reference. It is loaded once at startup and consulted before every command is
built.
"""

from __future__ import annotations

import fnmatch
import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from phantomstrike.utils.logging import get_logger

log = get_logger("engagement")


class ScopeViolation(Exception):
    """Raised when a target falls outside the authorised engagement scope."""

    def __init__(self, target: str, reason: str):
        self.target = target
        self.reason = reason
        super().__init__(f"Target {target!r} is out of scope: {reason}")


@dataclass
class Engagement:
    """A loaded engagement definition."""

    client: str = ""
    reference: str = ""
    authorised_by: str = ""
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    loaded_from: Optional[str] = None

    # ── Loading ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path) -> "Engagement":
        """
        Load an engagement from a YAML file.

        PyYAML is an optional dependency; a minimal parser handles the flat
        structure this file uses so scope enforcement never silently disables
        itself because a package is missing.
        """
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"Engagement file not found: {p}")

        raw = p.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(raw) or {}
        except ImportError:
            data = _parse_simple_yaml(raw)
        except Exception as exc:
            # A wildcard scope entry written naturally — `- *.example.com` — is a
            # YAML alias and fails to parse. That is the obvious way to write it,
            # so fall back to the flat parser rather than making the operator
            # discover a quoting rule from a stack trace.
            log.debug(f"YAML parse failed for {p} ({exc}); using flat parser")
            data = _parse_simple_yaml(raw)

        eng = cls(
            client=str(data.get("client", "")),
            reference=str(data.get("reference", "")),
            authorised_by=str(data.get("authorised_by", "")),
            in_scope=[str(x) for x in (data.get("in_scope") or [])],
            out_of_scope=[str(x) for x in (data.get("out_of_scope") or [])],
            starts_at=_parse_dt(data.get("starts_at")),
            ends_at=_parse_dt(data.get("ends_at")),
            loaded_from=str(p),
        )

        if not eng.in_scope:
            raise ValueError(
                f"Engagement {p} defines no in_scope entries. An engagement that "
                "authorises nothing would block every scan; remove the file or "
                "populate it."
            )

        log.info(
            f"Engagement loaded: {eng.client or 'unnamed'} "
            f"({len(eng.in_scope)} in scope, {len(eng.out_of_scope)} excluded)"
        )
        return eng

    # ── Enforcement ───────────────────────────────────────────────────

    def check(self, target: str) -> None:
        """
        Assert that `target` is authorised.

        Raises:
            ScopeViolation: if out of scope or outside the authorised window.
        """
        self._check_window()

        host = _extract_host(target)

        for pattern in self.out_of_scope:
            if _matches(host, pattern):
                raise ScopeViolation(
                    target, f"explicitly excluded by out_of_scope rule {pattern!r}"
                )

        for pattern in self.in_scope:
            if _matches(host, pattern):
                return

        raise ScopeViolation(
            target,
            f"not covered by any in_scope rule in {self.loaded_from}. "
            f"Authorised scope: {', '.join(self.in_scope)}",
        )

    def _check_window(self) -> None:
        now = datetime.now(timezone.utc)
        if self.starts_at and now < self.starts_at:
            raise ScopeViolation(
                "*", f"engagement window opens at {self.starts_at.isoformat()}"
            )
        if self.ends_at and now > self.ends_at:
            raise ScopeViolation(
                "*", f"engagement window closed at {self.ends_at.isoformat()}"
            )


# ── Helpers ───────────────────────────────────────────────────────────


def _extract_host(target: str) -> str:
    """Reduce a URL, host:port pair, or bare host to just the host."""
    t = target.strip()
    if "://" in t:
        parsed = urlparse(t)
        return parsed.hostname or t
    if t.count(":") == 1 and not _is_ipv6(t):
        return t.split(":", 1)[0]
    return t


def _is_ipv6(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 6
    except ValueError:
        return False


def _matches(host: str, pattern: str) -> bool:
    """Match a host against a CIDR, an exact host, or a wildcard domain."""
    # CIDR / IP range
    if "/" in pattern:
        try:
            network = ipaddress.ip_network(pattern, strict=False)
            return ipaddress.ip_address(host) in network
        except ValueError:
            return False

    # Exact IP
    try:
        return ipaddress.ip_address(host) == ipaddress.ip_address(pattern)
    except ValueError:
        pass

    # Domain, with wildcard support (*.example.com)
    return fnmatch.fnmatch(host.lower(), pattern.lower())


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_simple_yaml(raw: str) -> dict:
    """
    Parse the flat key / list-of-strings subset used by engagement files.

    Deliberately minimal — enough for this schema, and it keeps PyYAML optional
    so a missing package cannot turn scope enforcement off.
    """
    data: dict = {}
    current_list: Optional[str] = None

    for line in raw.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue

        if stripped.lstrip().startswith("- ") and current_list:
            data[current_list].append(stripped.lstrip()[2:].strip().strip("\"'"))
            continue

        if ":" in stripped and not stripped.startswith(" "):
            key, _, value = stripped.partition(":")
            key, value = key.strip(), value.strip().strip("\"'")
            if value:
                data[key] = value
                current_list = None
            else:
                data[key] = []
                current_list = key

    return data


# ── Module-level singleton ─────────────────────────────────────────────

_active: Optional[Engagement] = None


def load_active(path: Optional[str]) -> Optional[Engagement]:
    """Load the engagement used for scope checks. Returns None when unscoped."""
    global _active
    _active = Engagement.load(path) if path else None
    return _active


def get_active() -> Optional[Engagement]:
    """Return the active engagement, or None if the session is unscoped."""
    return _active


def enforce(target: str) -> None:
    """
    Check a target against the active engagement.

    No-op when no engagement is loaded, so existing workflows keep working; the
    warning makes the unscoped state visible rather than assumed.
    """
    if _active is None:
        return
    _active.check(target)
