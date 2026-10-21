"""Agnes Video 2.5 service — text-to-video and keyframe (image-to-video).

Official contract (https://agnes-ai.com/zh-Hans/docs/agnes-video-25):

    POST {base}/v1/videos                      create task -> {video_id, task_id, ...}
    GET  {base}/agnesapi?video_id=&model_name= poll task   -> {status, progress, url}

Request body: ``model``, ``prompt``, ``mode`` (text|keyframe|reference),
``seconds`` ("4"-"12"), ``size`` (720P|1080P|1K|2K), ``aspect_ratio``, ``seed``.

The API rejects (HTTP 400) the pre-2.5 parameters ``width``, ``height``,
``fps``, ``num_frames``, ``quality`` and ``num_inference_steps``. It also
rejects pixel strings for ``size`` and ``aspect_ratio: "auto"``.

All httpx calls bypass the system proxy to avoid silent failures.
"""

import asyncio
import logging
import time

import httpx
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse

from app.config import (
    AGNES_API_KEY,
    CREATE_VIDEO_URL,
    FLASH_VIDEO_SIZES,
    POLL_INTERVAL_SEC,
    POLL_TIMEOUT_SEC,
    QUERY_VIDEO_URL,
    VIDEO_MODEL,
)
from app.schemas import GenerateRequest, TaskResponse
from app.services.agnes_image import _ensure_png_data_uri

logger = logging.getLogger(__name__)

# Queue-full handling: the video service allows a single concurrent task and
# answers new requests with HTTP 503 / code "video_queue_full". Observed waits
# of up to ~7 minutes, so the retry budget is deliberately generous.
QUEUE_RETRY_ATTEMPTS = 30
QUEUE_RETRY_DELAY_SEC = 15

# Status-query transport retries (the API sometimes drops the connection
# mid-poll without returning a response).
QUERY_TRANSPORT_ATTEMPTS = 3

# How many consecutive failed status queries the polling loop tolerates
# before giving up on an otherwise healthy task.
POLL_MAX_CONSECUTIVE_ERRORS = 20

# Extra backoff when the status endpoint answers 429 (observed under load).
RATE_LIMIT_BACKOFF_SEC = 10


# ─── Internal helpers ──────────────────────────────────────────────


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    """Create an httpx client that bypasses the system proxy."""
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    """Build authorization headers for the Agnes API."""
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def _api_mode(req: GenerateRequest) -> str:
    """Map the UI mode onto the API's `mode` value."""
    return "keyframe" if req.mode == req.mode.img2vid else "text"


def _build_prompt(req: GenerateRequest) -> str:
    """Compose the final prompt.

    Video 2.5 has no ``negative_prompt`` field, so any negative prompt is
    folded into the prompt as an explicit "avoid" instruction.
    """
    prompt = req.prompt.strip()
    negative = (req.negative_prompt or "").strip()
    if negative:
        prompt = f"{prompt}\n\nAvoid the following: {negative}"
    return prompt


def _validate_model_and_size(req: GenerateRequest) -> None:
    """Reject combinations the API will refuse, with an actionable message."""
    if VIDEO_MODEL == "agnes-video-2.5-flash" and req.size not in FLASH_VIDEO_SIZES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{VIDEO_MODEL} 仅支持 size=720P（请求为 {req.size}）。"
                "如需 1080P/1K/2K，请把后端 .env 中的 AGNES_VIDEO_MODEL 设为 agnes-video-2.5（按秒计费）。"
            ),
        )


def _first_frame_value(image: str) -> str:
    """Normalise the uploaded image into the `first_frame` value.

    The image is re-encoded to PNG (the API is picky about format) and passed
    as a data URI, so no public hosting is required for image-to-video.
    """
    png_uri = _ensure_png_data_uri(image)
    logger.info("keyframe first_frame: png data URI, length=%d", len(png_uri))
    return png_uri


def _build_body(req: GenerateRequest) -> dict:
    """Build the create-task body for Video 2.5."""
    body: dict = {
        "model": VIDEO_MODEL,
        "prompt": _build_prompt(req),
        "mode": _api_mode(req),
        "seconds": str(req.seconds),   # API wants a string
        "size": req.size,
        "aspect_ratio": req.aspect_ratio,
    }

    if req.mode == req.mode.img2vid:
        if not req.image:
            raise HTTPException(status_code=400, detail="img2vid 模式需要上传一张参考图片")
        body["first_frame"] = _first_frame_value(req.image)

    if req.seed is not None:
        body["seed"] = req.seed

    return body


def _extract_video_id(data: dict) -> str:
    """Extract the polling ID. `video_id` is the documented query key."""
    for key in ("video_id", "id", "task_id"):
        val = data.get(key)
        if val:
            return str(val)
    raise HTTPException(status_code=500, detail="No video_id in Agnes API response")


def _extract_error_message(resp: httpx.Response) -> tuple[str, str]:
    """Return (code, message) from an error response."""
    code = ""
    message = "Unknown error"
    try:
        data = resp.json()
        code = str(data.get("code") or "")
        err = data.get("error")
        if isinstance(err, dict):
            message = err.get("message") or str(err)
        else:
            message = data.get("message") or data.get("detail") or str(data)
    except Exception:
        message = resp.text[:300]
    return code, message


# ─── Task lifecycle ────────────────────────────────────────────────


async def create_video_task(req: GenerateRequest) -> dict:
    """Submit a video task. Returns task metadata including the polling ID."""
    _validate_model_and_size(req)
    body = _build_body(req)

    logger.info(
        "Create video: model=%s mode=%s size=%s %ss %s, keys=%s, prompt=%s...",
        VIDEO_MODEL, body["mode"], req.size, req.seconds, req.aspect_ratio,
        list(body.keys()), req.prompt[:60],
    )

    async with _no_proxy_client(timeout=180) as client:
        for attempt in range(QUEUE_RETRY_ATTEMPTS + 1):
            resp = await client.post(CREATE_VIDEO_URL, headers=_get_headers(), json=body)

            if resp.status_code == 200:
                data = resp.json()
                video_id = _extract_video_id(data)
                logger.info(
                    "Task created: video_id=%s status=%s seconds=%s size=%s",
                    video_id, data.get("status"), data.get("seconds"), data.get("size"),
                )
                return {
                    "video_id": video_id,
                    "status": data.get("status", "queued"),
                    "model": VIDEO_MODEL,
                    "size": str(data.get("size") or req.size),
                    "seconds": req.seconds,
                }

            code, message = _extract_error_message(resp)

            # 503 / video_queue_full → the queue is busy; wait and retry.
            if resp.status_code == 503 or code == "video_queue_full":
                if attempt < QUEUE_RETRY_ATTEMPTS:
                    logger.warning(
                        "Video queue full (attempt %d/%d), retry in %ds",
                        attempt + 1, QUEUE_RETRY_ATTEMPTS, QUEUE_RETRY_DELAY_SEC,
                    )
                    await asyncio.sleep(QUEUE_RETRY_DELAY_SEC)
                    continue
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Agnes 视频队列已满（同一时间仅允许 1 个任务），"
                        f"已等待约 {QUEUE_RETRY_ATTEMPTS * QUEUE_RETRY_DELAY_SEC // 60} 分钟仍未空闲。"
                        "请稍后重试，或等待其他任务完成。"
                    ),
                )

            # 429 → back off once and retry
            if resp.status_code == 429 and attempt < QUEUE_RETRY_ATTEMPTS:
                await asyncio.sleep(30)
                continue

            logger.error(
                "Video create failed: HTTP %d code=%s message=%s | body=%s",
                resp.status_code, code, message, resp.text[:400],
            )
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Agnes API error ({code or resp.status_code}): {message}",
            )

    raise HTTPException(status_code=500, detail="Video task creation failed")


async def query_task_status(video_id: str) -> TaskResponse:
    """Query a task's current status.

    ``model_name`` is always sent: the docs require it for every mode except
    plain text, and it is the recommended polling form for all modes.

    Transient transport failures (the API occasionally drops the connection
    without a response) are retried here — otherwise a single network blip
    would kill a long-running generation.
    """
    last_error: Exception | None = None

    for attempt in range(QUERY_TRANSPORT_ATTEMPTS + 1):
        try:
            async with _no_proxy_client(timeout=30) as client:
                resp = await client.get(
                    QUERY_VIDEO_URL,
                    params={"video_id": video_id, "model_name": VIDEO_MODEL},
                    headers=_get_headers(),
                )
            break
        except httpx.TransportError as e:  # timeouts, disconnects, protocol errors
            last_error = e
            if attempt < QUERY_TRANSPORT_ATTEMPTS:
                logger.warning(
                    "Status query transport error (%s), retry %d/%d",
                    type(e).__name__, attempt + 1, QUERY_TRANSPORT_ATTEMPTS,
                )
                await asyncio.sleep(2)
                continue
            raise HTTPException(
                status_code=502,
                detail=f"查询任务状态时网络中断: {type(e).__name__}。任务仍在服务端运行，请稍后用同一 task_id 重试查询。",
            )
    else:  # pragma: no cover - loop always breaks or raises
        raise HTTPException(status_code=502, detail=str(last_error))

    if resp.status_code != 200:
        code, message = _extract_error_message(resp)
        logger.error("Query failed: HTTP %d code=%s %s", resp.status_code, code, message)
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"查询任务状态失败 ({code or resp.status_code}): {message}",
        )

    data = resp.json()
    status = data.get("status", "unknown")

    # The result URL is the top-level `url` field (documented).
    video_url = data.get("url") or data.get("video_url") or data.get("output_url")

    if status == "completed" and not video_url:
        logger.warning("Task completed without a URL. Full response: %s", str(data)[:800])
    if status == "failed":
        logger.error("Task failed: %s", data.get("error"))

    duration = None
    if data.get("seconds") is not None:
        try:
            duration = float(data["seconds"])
        except (TypeError, ValueError):
            duration = None

    error = data.get("error")
    if isinstance(error, dict):
        error = error.get("message") or str(error)

    return TaskResponse(
        task_id=video_id,
        status=status,
        video_url=video_url,
        duration=duration,
        progress=data.get("progress"),
        error=error,
    )


async def poll_until_complete(
    video_id: str,
    timeout: int = POLL_TIMEOUT_SEC,
    interval: int = POLL_INTERVAL_SEC,
) -> TaskResponse:
    """Poll until the task completes, fails, or the timeout elapses.

    A few consecutive query failures are tolerated: the generation keeps
    running server-side, so aborting on a transient network error would throw
    away a paid/queued task.
    """
    start = time.monotonic()
    consecutive_errors = 0

    while True:
        try:
            result = await query_task_status(video_id)
            consecutive_errors = 0
        except HTTPException as e:
            if e.status_code in (429, 502, 503, 504) and consecutive_errors < POLL_MAX_CONSECUTIVE_ERRORS:
                consecutive_errors += 1
                # 429 on this endpoint is load-based, not per-second pacing:
                # back off harder so the loop does not burn its error budget.
                wait = RATE_LIMIT_BACKOFF_SEC if e.status_code == 429 else interval
                logger.warning(
                    "Status query failed (%s), %d/%d tolerated, retry in %ds",
                    e.status_code, consecutive_errors, POLL_MAX_CONSECUTIVE_ERRORS, wait,
                )
                await asyncio.sleep(wait)
                continue
            raise

        if result.status == "completed":
            logger.info("Task %s completed in %ds: %s",
                        video_id, int(time.monotonic() - start), result.video_url)
            return result

        if result.status == "failed":
            return result

        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            logger.warning("Task %s timed out after %ds", video_id, int(elapsed))
            return TaskResponse(
                task_id=video_id,
                status="timeout",
                error=f"Timed out after {int(elapsed)} seconds",
            )

        await asyncio.sleep(interval)


# ─── Video proxy ───────────────────────────────────────────────────


async def proxy_video_stream(video_id: str, range_header: str | None) -> StreamingResponse:
    """Proxy the video with HTTP Range support (needed for seeking in <video>)."""
    status = await query_task_status(video_id)
    if status.status != "completed" or not status.video_url:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Current status: {status.status}",
        )

    video_url = status.video_url
    client = _no_proxy_client(timeout=None)

    try:
        # No Agnes auth headers: output URLs are on Agnes storage and reject the token.
        head_resp = await client.head(video_url)
        content_length = int(head_resp.headers.get("content-length", 0))
        content_type = head_resp.headers.get("content-type", "video/mp4")
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Failed to reach video URL: {e}")

    start_byte = 0
    end_byte = content_length - 1 if content_length > 0 else 0
    is_partial = False

    if range_header and "bytes=" in range_header:
        is_partial = True
        parts = range_header.split("bytes=")[1].split("-")
        start_byte = int(parts[0]) if parts[0] else 0
        if len(parts) > 1 and parts[1]:
            end_byte = int(parts[1])

    upstream_headers: dict = {}
    if is_partial:
        upstream_headers["Range"] = f"bytes={start_byte}-{end_byte}"

    upstream_req = client.build_request("GET", video_url, headers=upstream_headers)
    upstream_resp = await client.send(upstream_req, stream=True)

    if upstream_resp.status_code not in (200, 206):
        await upstream_resp.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned {upstream_resp.status_code}",
        )

    actual_length = int(upstream_resp.headers.get("content-length", 0))

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

    return StreamingResponse(stream_generator(), status_code=status_code, headers=resp_headers)


async def proxy_video_download(video_id: str) -> Response:
    """Download the video file as an attachment."""
    status = await query_task_status(video_id)
    if status.status != "completed" or not status.video_url:
        raise HTTPException(
            status_code=400,
            detail=f"Video not ready. Current status: {status.status}",
        )

    async with _no_proxy_client(timeout=180) as client:
        resp = await client.get(status.video_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to download video: {resp.status_code}")

        return Response(
            content=resp.content,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="video_{video_id}.mp4"',
                "Content-Length": str(len(resp.content)),
            },
        )
