"""Agnes Image 2.1 Flash API service — wrapper for image generation.

Handles: txt2img and img2img generation, PNG conversion, rate limiting,
image download and local storage.
All httpx calls bypass system proxy to avoid silent failures.
"""

import asyncio
import base64
import io
import logging
import time
import uuid
import httpx
from fastapi import HTTPException

from app.config import (
    AGNES_API_KEY,
    IMAGE_CREATE_URL,
    IMAGE_MODEL,
    IMAGE_RATE_LIMIT_COOLD,
    IMAGE_MAX_RETRIES,
    IMAGE_NETWORK_RETRY_DELAYS,
    UPLOADS_DIR,
)
from app.schemas import ImageGenerateRequest, ImageGenerateResponse

logger = logging.getLogger(__name__)

# Track last 4K request time for rate limiting
_last_4k_time: float = 0.0


# ─── Internal helpers ──────────────────────────────────────────────


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    """Create an httpx client that bypasses system proxy.

    System proxy causes silent failures when calling the Agnes API.
    Same pattern as the video service.
    """
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    """Build authorization headers for Agnes API."""
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def _ensure_png_data_uri(image_data: str) -> str:
    """Convert any image format to a PNG data URI.

    The Agnes Image API requires PNG format. If a WebP or JPEG is sent
    with a mismatched MIME type, the API silently falls back to text2img,
    causing image drift (the generated image looks nothing like the input).

    This function:
    1. Decodes the input (data URI or raw base64)
    2. Opens with Pillow (auto-detects format)
    3. Re-encodes as PNG data URI
    4. Raises an error if conversion fails (NEVER send mismatched MIME type)
    """
    from PIL import Image

    # Extract original MIME type for logging
    original_mime = "unknown"
    raw_b64 = image_data
    if image_data.startswith("data:"):
        idx = image_data.find(";base64,")
        if idx != -1:
            header = image_data[:idx]
            original_mime = header.split(":")[1] if ":" in header else "unknown"
            raw_b64 = image_data[idx + 8:]

    try:
        img_bytes = base64.b64decode(raw_b64)
        img = Image.open(io.BytesIO(img_bytes))
        original_format = img.format
        original_size = img.size
        original_mode = img.mode

        logger.info(
            "PNG conversion: original format=%s, mode=%s, size=%s, mime=%s, bytes=%d",
            original_format, original_mode, original_size, original_mime, len(img_bytes),
        )

        # Mode handling (matching reference implementation):
        # - RGBA/LA: keep as-is (preserve transparency)
        # - P with transparency: convert to RGBA
        # - Everything else: convert to RGB
        if img.mode in ("RGBA", "LA"):
            pass  # preserve transparency
        elif img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # Re-encode as PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        png_b64 = base64.b64encode(png_bytes).decode("ascii")

        logger.info(
            "PNG conversion OK: %s/%s → PNG, output bytes=%d, data_uri_len=%d",
            original_format, original_mode, len(png_bytes), len(png_b64) + 22,
        )

        return f"data:image/png;base64,{png_b64}"
    except Exception as e:
        # CRITICAL: Do NOT send the original data with a PNG MIME label.
        # That causes the Agnes API to silently fall back to text2img,
        # generating an image that looks nothing like the input.
        logger.error(
            "PNG conversion FAILED: %s. Original mime=%s, raw_b64_len=%d. "
            "Refusing to send mismatched MIME type to avoid silent text2img fallback.",
            e, original_mime, len(raw_b64),
        )
        raise HTTPException(
            status_code=400,
            detail=f"图片格式转换失败（{original_mime} → PNG），无法安全发送给 API。请尝试使用 PNG 格式的图片。错误: {e}",
        )


def _is_4k_size(size: str) -> bool:
    """Check if the requested size is in the 4K tier (subject to rate limiting)."""
    return size in ("3840x2160", "2160x3840", "4096x4096")


async def _enforce_rate_limit(size: str):
    """Wait if necessary to respect the 4K tier rate limit (1 req/60s)."""
    global _last_4k_time

    if not _is_4k_size(size):
        return

    now = time.monotonic()
    elapsed = now - _last_4k_time
    if elapsed < IMAGE_RATE_LIMIT_COOLD:
        wait = IMAGE_RATE_LIMIT_COOLD - elapsed
        logger.info("Rate limit: waiting %.1fs before 4K request", wait)
        await asyncio.sleep(wait)

    _last_4k_time = time.monotonic()


# ─── Core API call ─────────────────────────────────────────────────


async def _call_image_api(req: ImageGenerateRequest) -> dict:
    """Call the Agnes Image API and return the raw response data.

    Handles 429 rate limit retries and network error backoff.
    """
    # Build request body — send image in BOTH top-level and extra_body
    # to cover both LiteLLM proxy modes (top-level for httpx direct,
    # extra_body for SDK/curl compatibility)
    body: dict = {
        "model": IMAGE_MODEL,
        "prompt": req.prompt,
        "size": req.size,
    }

    # img2img: image MUST go in extra_body, NOT top-level body.
    # The LiteLLM proxy silently strips unknown top-level parameters (like "image"),
    # causing the API to fall back to text2img. extra_body is the correct channel
    # for non-standard parameters. Verified by diagnostic: extra_body.image → /i2i/ URL,
    # top-level image → /t2i/ URL (silent fallback).
    if req.mode == req.mode.img2img and req.image:
        png_uri = _ensure_png_data_uri(req.image)
        body["extra_body"] = {
            "image": [png_uri],
            "response_format": "url",
        }
        logger.info(
            "img2img request: prompt=%s..., size=%s, image_data_uri_len=%d, body_keys=%s",
            req.prompt[:50], req.size, len(png_uri), list(body.keys()),
        )
    else:
        logger.info("txt2img request: prompt=%s..., size=%s", req.prompt[:50], req.size)

    # Retry loop: handles 429 (rate limit) and network errors
    max_retries = IMAGE_MAX_RETRIES
    network_delays = IMAGE_NETWORK_RETRY_DELAYS

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with _no_proxy_client(timeout=240) as client:
                resp = await client.post(
                    IMAGE_CREATE_URL,
                    headers=_get_headers(),
                    json=body,
                )

            # 429 = rate limited → wait and retry
            if resp.status_code == 429:
                if attempt < max_retries:
                    wait = IMAGE_RATE_LIMIT_COOLD
                    logger.warning(
                        "Agnes Image API rate limited (429), retry %d/%d after %.0fs...",
                        attempt + 1,
                        max_retries,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise HTTPException(
                    status_code=429,
                    detail="图片生成 API 限流（4K 档每分钟仅允许 1 次请求），已自动重试 3 次仍被限流，请等待 1 分钟后重试",
                )

            # Other non-200 errors
            if resp.status_code != 200:
                error_detail = "Unknown error"
                try:
                    err_data = resp.json()
                    error_detail = (
                        err_data.get("error", {}).get("message")
                        or err_data.get("detail")
                        or err_data.get("message")
                        or str(err_data)
                    )
                except Exception:
                    error_detail = resp.text[:500]
                logger.error("Agnes Image API error %d: %s", resp.status_code, error_detail)
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Agnes API error: {error_detail}",
                )

            # Success
            data = resp.json()
            # Diagnostic: log full response to detect silent t2i fallback
            result_url = ""
            revised = ""
            if isinstance(data.get("data"), list) and len(data["data"]) > 0:
                result_url = data["data"][0].get("url") or ""
                revised = data["data"][0].get("revised_prompt") or ""
            logger.info(
                "API response: data_keys=%s, result_url=%s, revised_prompt=%s, "
                "url_has_t2i=%s, url_has_i2i=%s",
                list(data.keys()),
                result_url[:120],
                revised[:100] if revised else "(none)",
                "/t2i/" in result_url,
                "/i2i/" in result_url,
            )
            return data

        except HTTPException:
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
            last_error = e
            if attempt < max_retries and attempt < len(network_delays):
                delay = network_delays[attempt]
                logger.warning(
                    "Network error (%s), retry %d/%d after %ds...",
                    type(e).__name__,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            raise HTTPException(
                status_code=502,
                detail=f"网络错误，无法连接 Agnes API: {type(e).__name__}: {e}",
            )

    # Should not reach here
    raise HTTPException(status_code=500, detail=f"Image API call failed: {last_error}")


async def _download_and_save(image_url: str) -> str:
    """Download image from URL and save to local uploads directory.

    Returns the local URL path (e.g., "/uploads/generated-xxx.png").
    NOTE: Do NOT pass Authorization headers — image URLs are on Google Cloud Storage.
    """
    filename = f"generated-{uuid.uuid4().hex[:12]}.png"
    filepath = UPLOADS_DIR / filename

    async with _no_proxy_client(timeout=60) as client:
        # No auth headers — GCS doesn't recognize Agnes Bearer tokens
        resp = await client.get(image_url)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download generated image: {resp.status_code}",
            )
        filepath.write_bytes(resp.content)

    logger.info("Image saved to %s (%d bytes)", filepath, len(resp.content))
    return f"/uploads/{filename}"


# ─── Public API ────────────────────────────────────────────────────


async def generate_image(req: ImageGenerateRequest) -> ImageGenerateResponse:
    """Generate an image using the Agnes Image API.

    Flow:
    1. (img2img) Convert input image to PNG data URI
    2. Enforce rate limit for 4K tier
    3. Call POST /v1/images/generations (synchronous — returns result directly)
    4. Download the result image from GCS URL
    5. Save to local uploads/ directory
    6. Return local URL path
    """
    # Rate limiting for 4K sizes
    await _enforce_rate_limit(req.size)

    # Call the API
    data = await _call_image_api(req)

    # Parse response — result is in data[0]
    results = data.get("data", [])
    if not results:
        raise HTTPException(
            status_code=500,
            detail="Agnes Image API returned no results",
        )

    item = results[0]

    # Image can be returned as a URL or as base64
    image_url = item.get("url")
    b64_json = item.get("b64_json")
    revised_prompt = item.get("revised_prompt") or ""

    if b64_json:
        # Save base64 directly to disk
        filename = f"generated-{uuid.uuid4().hex[:12]}.png"
        filepath = UPLOADS_DIR / filename
        filepath.write_bytes(base64.b64decode(b64_json))
        local_url = f"/uploads/{filename}"
        logger.info("Image saved from b64_json to %s", filepath)
    elif image_url:
        # Download from GCS URL
        local_url = await _download_and_save(image_url)
    else:
        raise HTTPException(
            status_code=500,
            detail="Agnes Image API returned no image URL or base64 data",
        )

    return ImageGenerateResponse(
        image_url=local_url,
        revised_prompt=revised_prompt,
    )
