"""REST API endpoints for video generation."""

import logging
from fastapi import APIRouter, Request, HTTPException

from app.schemas import GenerateRequest, TaskResponse, CreateTaskResponse
from app.services import agnes_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["video"])


@router.post("", response_model=CreateTaskResponse)
async def create_task(req: GenerateRequest):
    """Submit a video generation task.

    Accepts txt2vid or img2vid mode with prompt and parameters.
    Returns a task_id that can be used to poll for status.
    """
    # Validate: img2vid mode requires image
    if req.mode == req.mode.img2vid and not req.image:
        raise HTTPException(
            status_code=400,
            detail="Image is required for img2vid mode",
        )

    task_id = await agnes_video.create_video_task(req)
    return CreateTaskResponse(task_id=task_id, status="queued")


@router.get("/{task_id}", response_model=TaskResponse)
async def get_status(task_id: str):
    """Query current task status (returns immediately)."""
    return await agnes_video.query_task_status(task_id)


@router.get("/{task_id}/wait", response_model=TaskResponse)
async def wait_for_completion(task_id: str, timeout: int = 600):
    """Long-poll: wait until the task completes, fails, or times out.

    Query parameter `timeout` controls the maximum wait in seconds (default 600).
    """
    return await agnes_video.poll_until_complete(task_id, timeout=timeout)


@router.get("/{task_id}/stream")
async def stream_video(task_id: str, request: Request):
    """Proxy video stream with HTTP Range support for browser playback.

    The browser's <video> tag can use this URL directly as the src.
    Supports seeking/scrubbing via Range requests.
    """
    range_header = request.headers.get("range")
    return await agnes_video.proxy_video_stream(task_id, range_header)


@router.get("/{task_id}/download")
async def download_video(task_id: str):
    """Download the generated video as a file attachment."""
    return await agnes_video.proxy_video_download(task_id)
