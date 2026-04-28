"""
PhantomStrike Database — async SQLite storage for scan results and history.

Uses aiosqlite for non-blocking database operations. Schema auto-creates on first run.
"""

from __future__ import annotations

import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from phantomstrike.config import settings
from phantomstrike.plugins.base import ToolResult
from phantomstrike.utils.logging import get_logger

log = get_logger("database")

# Extract the file path from the SQLite URL
_DB_PATH: str = ""


def _get_db_path() -> str:
    global _DB_PATH
    if not _DB_PATH:
        url = settings.database.url
        # Handle sqlite+aiosqlite:///path and sqlite:///path
        _DB_PATH = url.split("///", 1)[-1] if "///" in url else ":memory:"
    return _DB_PATH


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    tool_name TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    command_executed TEXT DEFAULT '',
    findings_json TEXT DEFAULT '[]',
    parsed_data_json TEXT DEFAULT '{}',
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    exit_code INTEGER DEFAULT -1,
    duration_seconds REAL DEFAULT 0.0,
    finding_counts_json TEXT DEFAULT '{}',
    error_message TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT DEFAULT '',
    finished_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_scan_target ON scan_results(target);
CREATE INDEX IF NOT EXISTS idx_scan_tool ON scan_results(tool_name);
CREATE INDEX IF NOT EXISTS idx_scan_created ON scan_results(created_at);
CREATE INDEX IF NOT EXISTS idx_scan_job ON scan_results(job_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    label TEXT DEFAULT '',
    role TEXT DEFAULT 'operator',
    created_at TEXT NOT NULL,
    last_used_at TEXT DEFAULT '',
    active INTEGER DEFAULT 1
);
"""


async def init_db() -> None:
    """Initialize database and create tables if needed."""
    db_path = _get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    log.info(f"Database initialized: {db_path}")


async def save_result(result: ToolResult, job_id: str = "") -> int:
    """
    Save a scan result to the database.

    Args:
        result: ToolResult from a plugin execution.
        job_id: Optional job ID for linking.

    Returns:
        Row ID of the inserted record.
    """
    db_path = _get_db_path()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """INSERT INTO scan_results
               (job_id, tool_name, target, status, command_executed,
                findings_json, parsed_data_json, stdout, stderr,
                exit_code, duration_seconds, finding_counts_json,
                error_message, created_at, started_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                result.tool_name,
                result.target,
                result.status.value,
                result.command_executed,
                json.dumps([f.to_dict() for f in result.findings]),
                json.dumps(result.parsed_data),
                result.stdout[-10000] if len(result.stdout) > 10000 else result.stdout,
                result.stderr[-5000] if len(result.stderr) > 5000 else result.stderr,
                result.exit_code,
                result.duration_seconds,
                json.dumps(result.finding_counts),
                result.error_message,
                datetime.now(timezone.utc).isoformat(),
                result.started_at,
                result.finished_at,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_results(
    target: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query scan results with optional filters."""
    db_path = _get_db_path()
    conditions = []
    params = []

    if target:
        conditions.append("target = ?")
        params.append(target)
    if tool_name:
        conditions.append("tool_name = ?")
        params.append(tool_name)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM scan_results {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_result_by_id(result_id: int) -> Optional[dict[str, Any]]:
    """Get a single result by ID."""
    db_path = _get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM scan_results WHERE id = ?", (result_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_stats() -> dict[str, Any]:
    """Get database statistics."""
    db_path = _get_db_path()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM scan_results")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT tool_name, COUNT(*) as cnt FROM scan_results GROUP BY tool_name ORDER BY cnt DESC"
        )
        tools = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT target, COUNT(*) as cnt FROM scan_results GROUP BY target ORDER BY cnt DESC LIMIT 10"
        )
        targets = await cursor.fetchall()

        return {
            "total_scans": total,
            "scans_by_tool": {row[0]: row[1] for row in tools},
            "top_targets": {row[0]: row[1] for row in targets},
        }
