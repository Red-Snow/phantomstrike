"""
PhantomStrike Job Routes — REST API for managing background jobs.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from phantomstrike.execution.queue import job_queue
from phantomstrike.storage import database
from phantomstrike.utils.logging import get_logger

log = get_logger("routes.jobs")

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
async def list_jobs():
    """List all jobs with their current status."""
    return {
        "jobs": job_queue.get_all_jobs(),
        "stats": job_queue.stats,
    }


@router.get("/jobs/active")
async def list_active_jobs():
    """List currently running/queued jobs."""
    return {"jobs": job_queue.get_active_jobs()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get details for a specific job."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job.to_dict()


@router.get("/jobs/{job_id}/output")
async def get_job_output(job_id: str, offset: int = 0):
    """
    Get streaming output from a running/completed job.

    Use offset to resume from a previous position (for polling).
    """
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    lines = job_queue.get_output(job_id, offset=offset)
    return {
        "job_id": job_id,
        "state": job.state.value,
        "offset": offset,
        "lines": lines,
        "total_lines": len(job.output_lines),
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    success = await job_queue.cancel(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' cannot be cancelled (not found or already completed)",
        )
    return {"success": True, "message": f"Job {job_id} cancel requested"}


@router.get("/history")
async def get_scan_history(
    target: str = None,
    tool_name: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """Query historical scan results from the database."""
    results = await database.get_results(
        target=target, tool_name=tool_name, limit=limit, offset=offset
    )
    return {"results": results, "count": len(results)}


@router.get("/history/stats")
async def get_history_stats():
    """Get database statistics."""
    return await database.get_stats()
