"""REST API endpoints for video generation."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app import history
from app.config import FAST_SUBMIT_TIMEOUT_SEC, POLL_TIMEOUT_SEC
from app.schemas import CreateTaskResponse, GenerateRequest, JobResponse, TaskResponse
from app.services import agnes_video

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["video"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])

TERMINAL = {"completed", "failed", "timeout"}


@router.post("", response_model=CreateTaskResponse)
async def create_task(req: GenerateRequest):
    """Submit a video generation task.

    Fast path: the task is accepted by Agnes → 200 with the Agnes task id.

    Queue-full path: the shared video queue allows only one task at a time, so a
    submit can be rejected for minutes. Instead of blocking the HTTP request
    (which always loses against the browser timeout and orphans the task), we
    return 202 immediately with a job id and keep retrying in the background.
    The client polls ``GET /api/jobs/{job_id}``.
    """
    if req.mode == req.mode.img2vid and not req.image:
        raise HTTPException(status_code=400, detail="img2vid 模式需要上传一张参考图片")

    reason = "queue_full"
    try:
        # Hard cap on the fast path: if submitting takes longer than this, fall
        # through to the background job instead of making the browser wait (and
        # eventually abort at its own timeout).
        info = await asyncio.wait_for(
            agnes_video.create_video_task(req, max_attempts=0),
            timeout=FAST_SUBMIT_TIMEOUT_SEC,
        )
        return CreateTaskResponse(
            task_id=info["video_id"],
            status=info["status"],
            model=info["model"],
            size=info["size"],
            seconds=info["seconds"],
        )
    except asyncio.TimeoutError:
        reason = "slow_submit"
        logger.info(
            "Fast submit exceeded %.0fs; handing off to the background job",
            FAST_SUBMIT_TIMEOUT_SEC,
        )
    except HTTPException as exc:
        if exc.status_code != 503:
            raise

    # Either the queue is full or the submit was too slow → hand off to the
    # background and return a job id right away.
    record = history.add_record(
        "video",
        status="submitting",
        prompt=req.prompt,
        model=agnes_video.VIDEO_MODEL,
        size=req.size,
        seconds=req.seconds,
        aspect_ratio=req.aspect_ratio,
        ui_mode=req.mode.value,
    )
    agnes_video.spawn_submit(record["id"], req)
    message = (
        f"提交耗时超过 {FAST_SUBMIT_TIMEOUT_SEC:.0f} 秒（参考图较大或网络较慢），已转后台继续提交"
        if reason == "slow_submit"
        else "视频队列已满，已在后台排队重试"
    )
    logger.info("Handed off as job %s (reason=%s)", record["id"], reason)
    return JSONResponse(
        status_code=202,
        content={
            "job_id": record["id"],
            "status": "submitting",
            "task_id": None,
            "prompt": req.prompt,
            "reason": reason,
            "message": f"{message}；可用 job_id 查询进度",
        },
    )


@jobs_router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Poll a queued job: covers both "still submitting" and "Agnes task running"."""
    record = history.get_record(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="没有该任务记录")

    task_id = record.get("task_id")
    if not task_id:
        return JobResponse(
            job_id=job_id,
            status=record.get("status", "submitting"),
            progress=record.get("progress"),
            error=record.get("error"),
            prompt=record.get("prompt"),
        )

    if record.get("status") in TERMINAL:
        return JobResponse(
            job_id=job_id,
            status=record["status"],
            task_id=task_id,
            video_url=record.get("remote_url"),
            local_url=record.get("local_url"),
            progress=record.get("progress"),
            error=record.get("error"),
            prompt=record.get("prompt"),
        )

    # Still running: refresh from Agnes (this also persists the finished file).
    result = await agnes_video.query_task_status(task_id)
    return JobResponse(
        job_id=job_id,
        status=result.status,
        task_id=task_id,
        video_url=result.video_url,
        local_url=result.local_url,
        progress=result.progress,
        error=result.error,
        prompt=record.get("prompt"),
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
