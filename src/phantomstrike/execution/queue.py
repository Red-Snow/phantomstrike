"""
PhantomStrike Job Queue — async background job management.

Allows tool executions to run in the background with:
- Job ID tracking
- Status polling
- Concurrent execution limits
- Job cancellation
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from phantomstrike.config import settings
from phantomstrike.execution.runner import runner
from phantomstrike.plugins.base import BaseToolPlugin, ToolResult, ToolStatus
from phantomstrike.utils.logging import get_logger

log = get_logger("queue")


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a queued or running tool execution."""
    id: str
    plugin_name: str
    params: dict[str, Any]
    state: JobState = JobState.QUEUED
    result: Optional[ToolResult] = None
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    output_lines: list[str] = field(default_factory=list)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "plugin_name": self.plugin_name,
            "params": self.params,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_line_count": len(self.output_lines),
        }
        if self.result:
            data["result"] = self.result.to_dict()
        return data


class JobQueue:
    """
    Manages background tool execution jobs.

    Features:
    - Concurrent execution limits
    - Job status tracking
    - Live output streaming
    - Cancellation support
    """

    def __init__(self, max_concurrent: int = 0):
        self._jobs: dict[str, Job] = {}
        max_concurrent = max_concurrent or settings.execution.max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    async def submit(
        self,
        plugin: BaseToolPlugin,
        params: dict[str, Any],
    ) -> str:
        """
        Submit a new job for background execution.

        Args:
            plugin: Tool plugin to run.
            params: Tool parameters.

        Returns:
            Job ID string.
        """
        job_id = str(uuid.uuid4())[:12]
        job = Job(id=job_id, plugin_name=plugin.name, params=params)
        self._jobs[job_id] = job

        log.info(f"Job [tool]{job_id}[/tool] queued: {plugin.name}")

        # Start execution in background
        job._task = asyncio.create_task(self._execute(job, plugin))

        return job_id

    async def _execute(self, job: Job, plugin: BaseToolPlugin) -> None:
        """Execute a job with concurrency limiting."""
        async with self._semaphore:
            job.state = JobState.RUNNING
            job.started_at = datetime.now(timezone.utc).isoformat()
            log.info(f"Job [tool]{job.id}[/tool] started: {plugin.name}")

            try:
                async def _stream_cb(line: str):
                    job.output_lines.append(line)

                result = await runner.run(
                    plugin, job.params, stream_callback=_stream_cb
                )
                job.result = result
                job.state = JobState.COMPLETED if result.success else JobState.FAILED

            except asyncio.CancelledError:
                job.state = JobState.CANCELLED
                log.info(f"Job [tool]{job.id}[/tool] cancelled")
            except Exception as e:
                job.state = JobState.FAILED
                job.result = ToolResult(
                    tool_name=plugin.name,
                    status=ToolStatus.FAILED,
                    target=job.params.get("target", "unknown"),
                    error_message=str(e),
                )
                log.error(f"Job [tool]{job.id}[/tool] failed: {e}")
            finally:
                job.completed_at = datetime.now(timezone.utc).isoformat()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list[dict]:
        """Get summary of all jobs."""
        return [job.to_dict() for job in self._jobs.values()]

    def get_active_jobs(self) -> list[dict]:
        """Get currently running jobs."""
        return [
            job.to_dict()
            for job in self._jobs.values()
            if job.state in (JobState.QUEUED, JobState.RUNNING)
        ]

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if not job or not job._task:
            return False
        if job.state in (JobState.QUEUED, JobState.RUNNING):
            job._task.cancel()
            job.state = JobState.CANCELLED
            log.info(f"Job [tool]{job_id}[/tool] cancel requested")
            return True
        return False

    def get_output(self, job_id: str, offset: int = 0) -> list[str]:
        """Get output lines from a job starting at offset."""
        job = self._jobs.get(job_id)
        if not job:
            return []
        return job.output_lines[offset:]

    @property
    def stats(self) -> dict[str, int]:
        """Queue statistics."""
        states: dict[str, int] = {}
        for job in self._jobs.values():
            key = job.state.value
            states[key] = states.get(key, 0) + 1
        return {
            "total": len(self._jobs),
            "max_concurrent": self._max_concurrent,
            **states,
        }


# Global job queue
job_queue = JobQueue()
