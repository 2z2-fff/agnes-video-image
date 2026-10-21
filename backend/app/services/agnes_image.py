"""Agnes Image 2.5 Flash service — wrapper for image generation.

Official contract (https://agnes-ai.com/en/docs/agnes-image-25-flash):

* ``POST {base}/v1/images/generations``
* text-to-image: ``model``, ``prompt``, ``size`` (tier 1K/2K/3K/4K) + ``ratio``
* image-to-image: input images go in ``extra_body.image`` as public URLs or
  Data URI Base64; ``extra_body.response_format`` must NOT be top-level.
* response: ``data[0].url`` or ``data[0].b64_json``

All httpx calls bypass the system proxy to avoid silent failures.
"""

import asyncio
import base64
import io
import logging
import uuid

import httpx
from fastapi import HTTPException

from app.config import (
    AGNES_API_KEY,
    IMAGE_CREATE_URL,
    IMAGE_MAX_RETRIES,
    IMAGE_MODEL,
    IMAGE_NETWORK_RETRY_DELAYS,
    IMAGE_RATE_LIMIT_COOLD,
    IMAGE_SERVICE_UNAVAIL_COOLD,
    UPLOADS_DIR,
)
from app.schemas import ImageGenerateRequest, ImageGenerateResponse

logger = logging.getLogger(__name__)


# ─── Internal helpers ──────────────────────────────────────────────


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    """Create an httpx client that bypasses the system proxy.

    A system proxy causes silent failures against the Agnes API.
    """
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    """Build authorization headers for the Agnes API."""
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def _ensure_png_data_uri(image_data: str) -> str:
    """Convert any image format to a PNG data URI.

    The image API only reliably honours image-to-image when the payload is a
    PNG data URI. A mismatched MIME type makes the service silently fall back
    to text-to-image, which shows up as "the result looks nothing like my input".
    """
    from PIL import Image

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

        if img.mode in ("RGBA", "LA"):
            pass  # preserve transparency
        elif img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        png_b64 = base64.b64encode(png_bytes).decode("ascii")

        logger.info(
            "PNG conversion OK: %s/%s -> PNG, output bytes=%d",
            original_format, original_mode, len(png_bytes),
        )
        return f"data:image/png;base64,{png_b64}"
    except Exception as e:
        logger.error(
            "PNG conversion FAILED: %s. Original mime=%s, raw_b64_len=%d. "
            "Refusing to send a mismatched MIME type (silent t2i fallback).",
            e, original_mime, len(raw_b64),
        )
        raise HTTPException(
            status_code=400,
            detail=f"图片格式转换失败（{original_mime} → PNG），无法安全发送给 API。请使用 PNG/JPG 图片。错误: {e}",
        )


# ─── Core API call ─────────────────────────────────────────────────


def _build_body(req: ImageGenerateRequest) -> dict:
    """Build the request body per the Image 2.5 Flash contract."""
    # response_format belongs in extra_body — a top-level copy is an error.
    extra: dict = {"response_format": "url"}

    if req.mode in (req.mode.img2img, req.mode.cartoon) and req.image:
        # image-to-image / cartoon: PNG data URI in extra_body.image
        extra["image"] = [_ensure_png_data_uri(req.image)]

    return {
        "model": IMAGE_MODEL,
        "prompt": req.prompt,
        "size": req.size,      # tier: 1K / 2K / 3K / 4K
        "ratio": req.ratio,    # 1:1 / 16:9 / 9:16 / ...
        "extra_body": extra,
    }


async def _call_image_api(req: ImageGenerateRequest) -> dict:
    """Call the image API, retrying rate limits, queue-full and network errors."""
    body = _build_body(req)

    logger.info(
        "Image request: mode=%s, model=%s, size=%s, ratio=%s, has_image=%s, prompt=%s...",
        req.mode, IMAGE_MODEL, req.size, req.ratio, "image" in body["extra_body"], req.prompt[:50],
    )

    max_retries = IMAGE_MAX_RETRIES
    network_delays = IMAGE_NETWORK_RETRY_DELAYS
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            async with _no_proxy_client(timeout=240) as client:
                resp = await client.post(IMAGE_CREATE_URL, headers=_get_headers(), json=body)

            # 429 = rate limited
            if resp.status_code == 429:
                if attempt < max_retries:
                    logger.warning(
                        "Image API rate limited (429), retry %d/%d after %.0fs",
                        attempt + 1, max_retries, IMAGE_RATE_LIMIT_COOLD,
                    )
                    await asyncio.sleep(IMAGE_RATE_LIMIT_COOLD)
                    continue
                raise HTTPException(
                    status_code=429,
                    detail=f"图片生成 API 限流，已重试 {max_retries} 次仍被限流，请稍后重试",
                )

            # 503 = queue full / service unavailable
            if resp.status_code == 503:
                if attempt < max_retries:
                    logger.warning(
                        "Image API unavailable (503), retry %d/%d after %.0fs",
                        attempt + 1, max_retries, IMAGE_SERVICE_UNAVAIL_COOLD,
                    )
                    await asyncio.sleep(IMAGE_SERVICE_UNAVAIL_COOLD)
                    continue
                raise HTTPException(
                    status_code=503,
                    detail=f"图片生成服务繁忙（队列已满），已重试 {max_retries} 次，请稍后重试",
                )

            if resp.status_code != 200:
                detail = "Unknown error"
                try:
                    err = resp.json()
                    detail = (
                        err.get("error", {}).get("message")
                        or err.get("message")
                        or err.get("detail")
                        or str(err)
                    )
                except Exception:
                    detail = resp.text[:500]
                logger.error("Image API error %d: %s | body=%s", resp.status_code, detail, resp.text[:300])
                raise HTTPException(status_code=resp.status_code, detail=f"Agnes API error: {detail}")

            data = resp.json()
            first = (data.get("data") or [{}])[0]
            logger.info(
                "Image API ok: keys=%s url=%s b64=%s route=%s",
                list(data.keys()),
                str(first.get("url"))[:110],
                "yes" if first.get("b64_json") else "no",
                "/i2i/" if "/i2i/" in str(first.get("url")) else "/t2i/",
            )
            return data

        except HTTPException:
            raise
        except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout,
                httpx.WriteTimeout, httpx.PoolTimeout) as e:
            last_error = e
            if attempt < max_retries and attempt < len(network_delays):
                delay = network_delays[attempt]
                logger.warning(
                    "Network error (%s), retry %d/%d after %ds",
                    type(e).__name__, attempt + 1, max_retries, delay,
                )
                await asyncio.sleep(delay)
                continue
            raise HTTPException(
                status_code=502,
                detail=f"网络错误，无法连接 Agnes API: {type(e).__name__}: {e}",
            )

    raise HTTPException(status_code=500, detail=f"Image API call failed: {last_error}")


async def _download_and_save(image_url: str) -> str:
    """Download the generated image and store it in uploads/.

    Output URLs live on Agnes storage (platform-outputs.agnes-ai.space), so the
    API bearer token must NOT be forwarded — those hosts reject it.
    """
    filename = f"generated-{uuid.uuid4().hex[:12]}.png"
    filepath = UPLOADS_DIR / filename

    async with _no_proxy_client(timeout=60) as client:
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
    """Generate an image (text-to-image or image-to-image) and store it locally."""
    data = await _call_image_api(req)

    results = data.get("data") or []
    if not results:
        raise HTTPException(status_code=500, detail="Agnes Image API returned no results")

    item = results[0]
    image_url = item.get("url")
    b64_json = item.get("b64_json")
    revised_prompt = item.get("revised_prompt") or ""

    if b64_json:
        filename = f"generated-{uuid.uuid4().hex[:12]}.png"
        filepath = UPLOADS_DIR / filename
        filepath.write_bytes(base64.b64decode(b64_json))
        local_url = f"/uploads/{filename}"
        logger.info("Image saved from b64_json to %s", filepath)
    elif image_url:
        local_url = await _download_and_save(image_url)
    else:
        raise HTTPException(status_code=500, detail="Agnes Image API returned no image URL or base64 data")

    return ImageGenerateResponse(
        image_url=local_url,
        revised_prompt=revised_prompt,
        size=req.size,
        ratio=req.ratio,
    )
