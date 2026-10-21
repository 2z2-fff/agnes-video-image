"""REST API endpoints for video generation."""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import POLL_TIMEOUT_SEC
from app.schemas import CreateTaskResponse, GenerateRequest, TaskResponse
from app.services import agnes_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["video"])


@router.post("", response_model=CreateTaskResponse)
async def create_task(req: GenerateRequest):
    """Submit a video generation task.

    txt2vid → Agnes `text` mode; img2vid → Agnes `keyframe` mode (first_frame).
    Returns a task id that can be polled for status.
    """
    if req.mode == req.mode.img2vid and not req.image:
        raise HTTPException(status_code=400, detail="img2vid 模式需要上传一张参考图片")

    info = await agnes_video.create_video_task(req)
    return CreateTaskResponse(
        task_id=info["video_id"],
        status=info["status"],
        model=info["model"],
        size=info["size"],
        seconds=info["seconds"],
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_status(task_id: str):
    """Query current task status (returns immediately)."""
    return await agnes_video.query_task_status(task_id)


@router.get("/{task_id}/wait", response_model=TaskResponse)
async def wait_for_completion(task_id: str, timeout: int = POLL_TIMEOUT_SEC):
    """Long-poll: wait until the task completes, fails, or times out."""
    return await agnes_video.poll_until_complete(task_id, timeout=timeout)


@router.get("/{task_id}/stream")
async def stream_video(task_id: str, request: Request):
    """Proxy the video stream with HTTP Range support for browser playback."""
    range_header = request.headers.get("range")
    return await agnes_video.proxy_video_stream(task_id, range_header)


@router.get("/{task_id}/download")
async def download_video(task_id: str):
    """Download the generated video as a file attachment."""
    return await agnes_video.proxy_video_download(task_id)
