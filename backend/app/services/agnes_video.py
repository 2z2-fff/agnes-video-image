"""Agnes Video V2.0 API service — core wrapper for all video generation operations.

Handles: task creation, status querying, polling, video stream/download proxy.
All httpx calls bypass system proxy to avoid silent failures.
"""

import asyncio
import time
import logging
import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, Response

from app.config import (
    AGNES_API_KEY,
    CREATE_VIDEO_URL,
    QUERY_VIDEO_URL,
    AGNES_MODEL,
    ASPECT_MAP,
    POLL_INTERVAL_SEC,
    POLL_TIMEOUT_SEC,
)
from app.schemas import GenerateRequest, TaskResponse
from app.services.agnes_image import _ensure_png_data_uri

logger = logging.getLogger(__name__)


# ─── Internal helpers ──────────────────────────────────────────────


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    """Create an httpx client that bypasses system proxy.

    System proxy causes silent failures (no error, no response) when
    calling the Agnes API. This is the #1 gotcha.
    """
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    """Build authorization headers for Agnes API."""
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def _frames_for_duration(seconds: float, fps: int = 24) -> int:
    """Convert desired duration in seconds to a valid num_frames value.

    Agnes API requires: num_frames = 8n + 1.
    Resolution-tier limits (our ASPECT_MAP falls in 720p tier):
      1080p: max 169 frames (~7s @24fps)
      720p:  max 409 frames (~17s @24fps)
      480p:  max 961 frames (~40s @24fps)
    """
    MAX_N = 51  # 8*51+1 = 409 (720p tier limit)
    target = int(seconds * fps)
    n = round((target - 1) / 8)
    n = max(1, min(n, MAX_N))
    return 8 * n + 1


def _strip_data_uri(image_str: str) -> str:
    """Strip data URI prefix if present, returning pure base64.

    e.g. "data:image/png;base64,AAAA..." → "AAAA..."
    """
    if image_str.startswith("data:"):
        # Find the base64 marker
        idx = image_str.find(";base64,")
        if idx != -1:
            return image_str[idx + 8 :]
    return image_str


def _extract_task_id(data: dict) -> str:
    """Extract task ID from Agnes API response, handling multiple field names."""
    for key in ("video_id", "id", "task_id"):
        val = data.get(key)
        if val:
            return str(val)
    raise HTTPException(status_code=500, detail="No task ID found in Agnes API response")


# ─── Task lifecycle ────────────────────────────────────────────────


async def create_video_task(req: GenerateRequest) -> str:
    """Submit a video generation task to Agnes API. Returns the task ID.

    Endpoint: POST https://apihub.agnes-ai.com/v1/videos
    """
    # Resolve resolution from aspect ratio
    width, height = ASPECT_MAP.get(req.aspect_ratio, (1152, 648))

    # Calculate valid num_frames from desired duration
    num_frames = _frames_for_duration(req.duration, req.fps)

    # Build request body
    body: dict = {
        "model": AGNES_MODEL,
        "prompt": req.prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "frame_rate": req.fps,
    }

    # img2vid: image MUST go in extra_body.image, NOT top-level body.
    # The LiteLLM proxy strips unknown top-level parameters (like "image"),
    # causing img2vid requests to fail with 404 NotFoundError.
    # Fix: move image to extra_body.image (array of pure base64 strings).
    # Diagnostic test (2026-07-03) confirmed: extra_body.image with pure base64 → 200 OK.
    # The image is converted to PNG first (handles WebP/JPEG → PNG for format compatibility),
    # then the data URI prefix is stripped to get pure base64.
    if req.mode == req.mode.img2vid and req.image:
        # Step 1: Convert to PNG data URI (handles any format → PNG)
        png_uri = _ensure_png_data_uri(req.image)
        # Step 2: Strip data URI prefix → pure base64 (confirmed working format)
        pure_b64 = _strip_data_uri(png_uri)
        body["extra_body"] = {
            "image": [pure_b64],  # array of pure base64 strings
        }
        logger.info(
            "img2vid request: prompt=%s..., image_b64_len=%d, body_keys=%s",
            req.prompt[:50], len(pure_b64), list(body.keys()),
        )

    # Optional parameters (only add if non-empty/non-None)
    if req.negative_prompt:
        body["negative_prompt"] = req.negative_prompt
    if req.seed is not None:
        body["seed"] = req.seed
    if req.num_inference_steps and req.num_inference_steps != 25:
        body["num_inference_steps"] = req.num_inference_steps

    logger.info(
        "Creating video task: mode=%s, prompt=%s..., %dx%d, %d frames @ %d fps, has_extra_body=%s",
        req.mode,
        req.prompt[:50],
        width,
        height,
        num_frames,
        req.fps,
        "extra_body" in body,
    )

    # Agnes API allows only 1 concurrent task. On 503 "Service busy", retry with backoff.
    MAX_503_RETRIES = 5
    RETRY_DELAY_SEC = 15

    async with _no_proxy_client(timeout=120) as client:
        for attempt in range(MAX_503_RETRIES + 1):
            resp = await client.post(
                CREATE_VIDEO_URL,
                headers=_get_headers(),
                json=body,
            )

            # 503 = service busy (another task still running) → wait and retry
            if resp.status_code == 503:
                if attempt < MAX_503_RETRIES:
                    logger.warning(
                        "Agnes API busy (503), retry %d/%d after %ds...",
                        attempt + 1,
                        MAX_503_RETRIES,
                        RETRY_DELAY_SEC,
                    )
                    await asyncio.sleep(RETRY_DELAY_SEC)
                    continue
                # Max retries exhausted
                raise HTTPException(
                    status_code=503,
                    detail="Agnes API 服务繁忙（可能有其他任务正在运行），已自动重试 5 次仍无法创建任务，请等待 1-2 分钟后重试",
                )

            # Other non-200 errors: no retry
            if resp.status_code != 200:
                error_detail = "Unknown error"
                try:
                    err_data = resp.json()
                    # LiteLLM returns errors nested as {"error": {"message": "...", "type": null, "param": null, "code": "404"}}
                    # Try nested error.message first, then flat fields
                    err_obj = err_data.get("error")
                    if isinstance(err_obj, dict):
                        error_detail = err_obj.get("message") or str(err_obj)
                    else:
                        error_detail = (
                            err_data.get("detail")
                            or err_data.get("message")
                            or str(err_data)
                        )
                except Exception:
                    error_detail = resp.text[:500]
                logger.error(
                    "Agnes API error %d: %s | Full response body: %s | Request body keys: %s, has_extra_body: %s",
                    resp.status_code,
                    error_detail,
                    resp.text[:500],
                    list(body.keys()),
                    "extra_body" in body,
                )
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Agnes API error: {error_detail}",
                )

            # Success
            break

    data = resp.json()
    logger.info(
        "API response: status_code=%d, response_keys=%s, body_keys=%s",
        resp.status_code,
        list(data.keys()),
        list(body.keys()),
    )
    task_id = _extract_task_id(data)
    logger.info("Task created: %s", task_id)
    return task_id


async def query_task_status(task_id: str) -> TaskResponse:
    """Query current status of a video task.

    Endpoint: GET https://apihub.agnes-ai.com/agnesapi?video_id=<task_id>
    """
    async with _no_proxy_client(timeout=30) as client:
        resp = await client.get(
            QUERY_VIDEO_URL,
            params={"video_id": task_id},
            headers=_get_headers(),
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Failed to query task status: {resp.text[:200]}",
        )

    data = resp.json()
    status = data.get("status", "unknown")

    # Diagnostic: log all response keys when completed, to find the video URL field
    if status == "completed":
        logger.info("Task completed. Response keys: %s", list(data.keys()))
        # Log all non-None values that could be URLs
        for k, v in data.items():
            if v is not None and isinstance(v, str) and (v.startswith("http") or "url" in k.lower() or "video" in k.lower()):
                logger.info("  Field '%s' = %s", k, v[:120])

    # Extract video URL — check multiple possible field names
    video_url = (
        data.get("remixed_from_video_id")
        or data.get("video_url")
        or data.get("url")
        or data.get("output_url")
        or data.get("result_url")
        or data.get("download_url")
    )

    # If still None and status is completed, log the full response for debugging
    if status == "completed" and not video_url:
        logger.warning("Task completed but no video URL found! Full response: %s", str(data)[:1000])

    # Extract duration
    duration = None
    seconds_raw = data.get("seconds")
    if seconds_raw:
        try:
            duration = float(seconds_raw)
        except (ValueError, TypeError):
            pass

    error = data.get("error")

    return TaskResponse(
        task_id=task_id,
        status=status,
        video_url=video_url,
        duration=duration,
        error=error,
    )


async def poll_until_complete(
    task_id: str,
    timeout: int = POLL_TIMEOUT_SEC,
    interval: int = POLL_INTERVAL_SEC,
) -> TaskResponse:
    """Poll task status until completed, failed, or timeout.

    Returns the final TaskResponse. If timeout, returns with status="timeout".
    """
    start = time.monotonic()

    while True:
        result = await query_task_status(task_id)

        if result.status == "completed":
            logger.info("Task %s completed: %s", task_id, result.video_url)
            return result

        if result.status == "failed":
            logger.error("Task %s failed: %s", task_id, result.error)
            return result

        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            logger.warning("Task %s timed out after %ds", task_id, int(elapsed))
            return TaskResponse(
                task_id=task_id,
                status="timeout",
                error=f"Timed out after {int(elapsed)} seconds",
            )

        # Wait before next poll
        await asyncio.sleep(interval)


# ─── Video proxy ───────────────────────────────────────────────────


async def proxy_video_stream(task_id: str, range_header: str | None) -> StreamingResponse:
    """Proxy video stream from Agnes storage to browser, supporting HTTP Range.

    This is necessary because:
    1. Agnes video URLs have CORS restrictions (can't play directly in <video>)
    2. Browser needs Range support for seeking/scrubbing
    """
    # First, get the actual video URL from task status
    status = await query_task_status(task_id)
    if status.status != "completed" or not status.video_url:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Current status: {status.status}",
        )

    video_url = status.video_url

    # Use a single client for both HEAD and streaming GET
    client = _no_proxy_client(timeout=None)  # no timeout for streaming

    try:
        # HEAD request to get content metadata
        # NOTE: Do NOT pass Agnes auth headers — the video URL is on Google Cloud Storage,
        # not apihub.agnes-ai.com. Sending the Agnes Bearer token causes 401.
        head_resp = await client.head(video_url)
        content_length = int(head_resp.headers.get("content-length", 0))
        content_type = head_resp.headers.get("content-type", "video/mp4")
        accept_ranges = head_resp.headers.get("accept-ranges", "bytes")
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Failed to reach video URL: {e}")

    # Parse Range header if present
    start_byte = 0
    end_byte = content_length - 1 if content_length > 0 else 0
    is_partial = False

    if range_header and "bytes=" in range_header:
        is_partial = True
        range_spec = range_header.split("bytes=")[1]
        parts = range_spec.split("-")
        start_byte = int(parts[0]) if parts[0] else 0
        if len(parts) > 1 and parts[1]:
            end_byte = int(parts[1])

    # Build upstream request headers — no auth, video URL is on Google Cloud Storage
    upstream_headers: dict = {}
    if is_partial:
        upstream_headers["Range"] = f"bytes={start_byte}-{end_byte}"

    # Stream the video content
    upstream_req = client.build_request(
        "GET",
        video_url,
        headers=upstream_headers,
    )
    upstream_resp = await client.send(upstream_req, stream=True)

    if upstream_resp.status_code not in (200, 206):
        await upstream_resp.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned {upstream_resp.status_code}",
        )

    actual_length = int(upstream_resp.headers.get("content-length", 0))

    # Build response headers
    resp_headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
    }

    if is_partial:
        resp_headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{content_length}"
        resp_headers["Content-Length"] = str(actual_length)
        status_code = 206
    else:
        resp_headers["Content-Length"] = str(content_length)
        status_code = 200

    async def stream_generator():
        try:
            async for chunk in upstream_resp.aiter_raw():
                yield chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=status_code,
        headers=resp_headers,
    )


async def proxy_video_download(task_id: str) -> Response:
    """Download video file as an attachment."""
    status = await query_task_status(task_id)
    if status.status != "completed" or not status.video_url:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Current status: {status.status}",
        )

    async with _no_proxy_client(timeout=120) as client:
        # NOTE: No auth headers — video URL is on Google Cloud Storage, not Agnes API.
        resp = await client.get(status.video_url)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download video: {resp.status_code}",
            )

        return Response(
            content=resp.content,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="video_{task_id}.mp4"',
                "Content-Length": str(len(resp.content)),
            },
        )
