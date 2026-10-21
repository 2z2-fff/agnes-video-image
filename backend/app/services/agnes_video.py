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
    QUEUE_WAIT_MINUTES,
    REF_IMAGE_MAX_SIDE,
    REF_TOTAL_MAX_MB,
    VIDEO_DIR,
    VIDEO_MODEL,
    max_reference_images,
)
from app import history
from app.schemas import GenerateRequest, TaskResponse
from app.services.agnes_image import _ensure_png_data_uri

logger = logging.getLogger(__name__)

# Queue-full handling: the video service allows a single concurrent task and
# answers new requests with HTTP 503 / code "video_queue_full". The queue is
# shared platform-wide and can stay saturated for hours (verified: none of our
# own tasks were holding it), so the background retries with escalating delays
# within a configurable budget instead of blocking any HTTP request.
QUEUE_WAIT_SEC = QUEUE_WAIT_MINUTES * 60
QUEUE_RETRY_DELAYS = [15, 30, 60]   # escalate to stop hammering the endpoint

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
    return {
        req.mode.txt2vid: "text",
        req.mode.img2vid: "keyframe",
        req.mode.reference: "reference",
    }[req.mode]


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

    if req.mode == req.mode.reference:
        limit = max_reference_images()
        count = len([i for i in (req.images or []) if i])
        if count > limit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{VIDEO_MODEL} 的参考图片上限为 {limit} 张（本次 {count} 张）。"
                    "如需更多，请把 AGNES_VIDEO_MODEL 设为 agnes-video-2.5（上限 8 张）。"
                ),
            )


async def _encode_image(image: str) -> str:
    """Encode one uploaded image to a downscaled PNG data URI.

    Runs in a worker thread: PIL decode/encode on a large photo takes seconds,
    and doing that on the event loop would stall status polling for every other
    request in flight.
    """
    return await asyncio.to_thread(_ensure_png_data_uri, image, REF_IMAGE_MAX_SIDE)


async def _build_body(req: GenerateRequest) -> dict:
    """Build the create-task body for Video 2.5.

    Media routing (mutually exclusive, enforced by the schema):

    * ``keyframe``  -> ``first_frame`` and optional ``last_frame``
    * ``reference`` -> ``images`` array (referenced as <Picture N> in the prompt)
    """
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
        body["first_frame"] = await _encode_image(req.image)
        if req.last_image:
            # first + last frame pair turns the task into a controlled transition
            body["last_frame"] = await _encode_image(req.last_image)

    elif req.mode == req.mode.reference:
        refs = [i for i in (req.images or []) if i]
        if not refs:
            raise HTTPException(status_code=400, detail="多图参考模式至少需要上传 1 张图片")
        encoded = [await _encode_image(i) for i in refs]
        body["images"] = encoded
        logger.info(
            "reference mode: %d image(s), total payload=%.1f MB",
            len(encoded), sum(len(e) for e in encoded) / 1024 / 1024,
        )

        if "<Picture" not in req.prompt:
            logger.warning(
                "reference mode prompt has no <Picture N> placeholder; "
                "the docs recommend naming each reference explicitly."
            )

    if req.seed is not None:
        body["seed"] = req.seed

    # The API caps a request at 50MB; fail fast with guidance instead of letting
    # the provider reject (or the upload time out) on a huge payload.
    total_bytes = sum(len(v) for v in (body.get("images") or []))
    total_bytes += len(body.get("first_frame") or "") + len(body.get("last_frame") or "")
    if total_bytes > REF_TOTAL_MAX_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=(
                f"参考图片总体积过大（约 {total_bytes // 1024 // 1024} MB，上限 {REF_TOTAL_MAX_MB} MB）。"
                "请减少图片数量或改用更小的图片（服务端已自动压缩到 "
                f"{REF_IMAGE_MAX_SIDE}px 长边，仍超限时可先自行缩小）。"
            ),
        )

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


async def create_video_task(
    req: GenerateRequest,
    max_attempts: int = 1,
    record_id: str | None = None,
) -> dict:
    """Submit a video task. Returns task metadata including the polling ID.

    ``max_attempts=0`` performs a single non-blocking attempt: if the shared
    queue is full it raises 503 immediately so the HTTP request can return and
    the retrying can continue in the background (a long blocked request always
    loses the race against a client timeout, orphaning the task).

    ``max_attempts>=1`` retries within ``QUEUE_WAIT_MINUTES`` with escalating
    delays — that is what the background worker uses.

    ``record_id`` reuses an existing history record instead of creating one.
    """
    _validate_model_and_size(req)
    body = await _build_body(req)

    logger.info(
        "Create video: model=%s mode=%s size=%s %ss %s, keys=%s, prompt=%s...",
        VIDEO_MODEL, body["mode"], req.size, req.seconds, req.aspect_ratio,
        list(body.keys()), req.prompt[:60],
    )

    async with _no_proxy_client(timeout=180) as client:
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            resp = await client.post(CREATE_VIDEO_URL, headers=_get_headers(), json=body)

            if resp.status_code == 200:
                data = resp.json()
                video_id = _extract_video_id(data)
                logger.info(
                    "Task created: video_id=%s status=%s seconds=%s size=%s",
                    video_id, data.get("status"), data.get("seconds"), data.get("size"),
                )
                # Persist immediately: an in-flight task must survive a page reload.
                fields = dict(
                    task_id=video_id,
                    prompt=req.prompt,
                    mode=body["mode"],
                    ui_mode=req.mode.value,
                    model=VIDEO_MODEL,
                    size=str(data.get("size") or req.size),
                    seconds=req.seconds,
                    aspect_ratio=req.aspect_ratio,
                    status=data.get("status", "queued"),
                    error=None,
                )
                if record_id:
                    history.update_record(record_id=record_id, **fields)
                else:
                    history.add_record("video", **fields)
                return {
                    "video_id": video_id,
                    "status": data.get("status", "queued"),
                    "model": VIDEO_MODEL,
                    "size": str(data.get("size") or req.size),
                    "seconds": req.seconds,
                }

            code, message = _extract_error_message(resp)

            # 503 / video_queue_full → the queue is busy; retry within budget.
            if resp.status_code == 503 or code == "video_queue_full":
                elapsed = time.monotonic() - started
                if max_attempts == 0 or elapsed >= QUEUE_WAIT_SEC:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Agnes 视频队列已满（平台共享，同一时间仅允许 1 个任务），"
                            f"已排队等待约 {int(elapsed // 60)} 分钟仍未空闲"
                            f"（上限 {QUEUE_WAIT_MINUTES} 分钟）；本次未创建任务、未计费，请稍后重试"
                        ),
                    )
                delay = QUEUE_RETRY_DELAYS[min(attempt - 1, len(QUEUE_RETRY_DELAYS) - 1)]
                logger.warning(
                    "Video queue full (attempt %d, waited %ds), retry in %ds",
                    attempt, int(elapsed), delay,
                )
                await asyncio.sleep(delay)
                continue

            # 429 → back off once and retry
            if resp.status_code == 429:
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


# ─── Background submission (queue-full path) ──────────────────────

# record_id -> task, so the user can cancel a queue wait and we can keep a
# strong reference (the event loop would otherwise garbage-collect it).
_submit_jobs: dict[str, asyncio.Task] = {}


async def _submit_worker(record_id: str, req: GenerateRequest) -> None:
    """Retry submitting until accepted, then attach the Agnes task id."""
    try:
        await create_video_task(req, max_attempts=1, record_id=record_id)
    except asyncio.CancelledError:
        logger.info("Background submit cancelled (record %s)", record_id)
        raise
    except HTTPException as exc:
        logger.warning("Background submit failed (record %s): %s", record_id, exc.detail)
        history.update_record(record_id=record_id, status="failed", error=str(exc.detail))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Background submit crashed (record %s)", record_id)
        history.update_record(record_id=record_id, status="failed", error=str(exc))


def spawn_submit(record_id: str, req: GenerateRequest) -> None:
    """Start a background submit retry loop for a queued generation."""
    task = asyncio.create_task(_submit_worker(record_id, req))
    _submit_jobs[record_id] = task

    def _cleanup(_: asyncio.Task) -> None:
        _submit_jobs.pop(record_id, None)

    task.add_done_callback(_cleanup)


def cancel_submit(record_id: str) -> bool:
    """Stop a queued (not yet submitted) job. Returns True if one was running."""
    task = _submit_jobs.pop(record_id, None)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


async def _persist_video_file(video_id: str, remote_url: str) -> str | None:
    """Download a finished video into ``uploads/videos`` and return its local URL.

    Idempotent: an existing non-empty file is reused, so repeated polling is cheap.
    Without this, the only copy of a result lives on Agnes' storage and is lost
    as soon as the UI forgets the task id.
    """
    target = VIDEO_DIR / f"{video_id}.mp4"
    if target.exists() and target.stat().st_size > 0:
        return f"/uploads/videos/{target.name}"

    try:
        async with _no_proxy_client(timeout=300) as client:
            # No Agnes auth header: storage hosts reject the API bearer token.
            resp = await client.get(remote_url)
        if resp.status_code != 200:
            logger.warning("Persist video failed: HTTP %s", resp.status_code)
            return None
        target.write_bytes(resp.content)
        logger.info("Video persisted: %s (%d bytes)", target, len(resp.content))
        return f"/uploads/videos/{target.name}"
    except Exception as e:
        logger.warning("Persist video error: %s", e)
        return None


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

    # Persist the finished file + keep the history record in sync, so the result
    # survives page reloads and Agnes' link expiry.
    local_url = None
    if status == "completed" and video_url:
        local_url = await _persist_video_file(video_id, video_url)

    updated = history.update_record(
        by_task_id=video_id,
        status=status,
        remote_url=video_url,
        local_url=local_url,
        error=error,
        progress=data.get("progress"),
    )
    # Self-healing: a task created before history existed (or whose record was
    # lost) still shows up once it reaches a terminal state.
    if updated is None and status in ("completed", "failed"):
        history.add_record(
            "video",
            task_id=video_id,
            prompt=None,
            model=VIDEO_MODEL,
            status=status,
            local_url=local_url,
            remote_url=video_url,
            error=error,
        )

    return TaskResponse(
        task_id=video_id,
        status=status,
        video_url=video_url,
        local_url=local_url,
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
