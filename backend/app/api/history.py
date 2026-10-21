"""Generation history endpoints.

Lets the UI restore previous results after a page reload or a view switch:
the records are written by the video/image services, and finished videos are
also stored on disk under ``uploads/videos``.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app import history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    kind: str | None = Query(None, description="image | video"),
):
    """Return the newest generations (default 50)."""
    items = history.list_records(limit=limit, kind=kind)
    return {"items": items, "count": len(items)}


@router.get("/by-task/{task_id}")
async def get_by_task(task_id: str):
    """Look up a video record by its Agnes task id (used to resume polling)."""
    record = history.find_by_task(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="没有该任务的记录")
    return record


@router.delete("/{record_id}")
async def delete_history(record_id: str):
    """Remove a record from the list (the stored file is kept)."""
    if not history.delete_record(record_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"deleted": record_id}
