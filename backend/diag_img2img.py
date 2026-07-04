"""Diagnostic script: test Agnes Image API img2img vs txt2img.

Creates a small test image, sends both img2img and txt2img requests,
and compares the result URLs to detect silent t2i fallback.

Usage: python diag_img2img.py
"""

import asyncio
import base64
import io
import json
import os
import sys
import httpx
from PIL import Image

# Load .env
from dotenv import load_dotenv
load_dotenv()

AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com")
IMAGE_CREATE_URL = f"{AGNES_BASE_URL}/v1/images/generations"
IMAGE_MODEL = "agnes-image-2.1-flash"

if not AGNES_API_KEY:
    print("ERROR: AGNES_API_KEY not set in .env")
    sys.exit(1)


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def create_test_image() -> str:
    """Create a distinctive test image (red square with text) and return as PNG data URI."""
    img = Image.new("RGB", (256, 256), color=(255, 0, 0))  # bright red
    # Add some text to make it distinctive
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.text((50, 120), "TEST IMG2IMG", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_uri = f"data:image/png;base64,{png_b64}"
    print(f"Test image created: 256x256 red PNG, data_uri_len={len(data_uri)}")
    return data_uri


async def test_request(label: str, body: dict) -> dict:
    """Send a request to the Agnes API and log the full response."""
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"Body keys: {list(body.keys())}")
    if "image" in body:
        print(f"Image data URI length: {len(body['image'][0])}")
    print(f"Prompt: {body.get('prompt', '')[:100]}")
    print(f"{'='*60}")

    async with _no_proxy_client(timeout=240) as client:
        resp = await client.post(
            IMAGE_CREATE_URL,
            headers=_get_headers(),
            json=body,
        )

    print(f"Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Error: {resp.text[:500]}")
        return {}

    data = resp.json()
    print(f"Response keys: {list(data.keys())}")

    if isinstance(data.get("data"), list) and len(data["data"]) > 0:
        item = data["data"][0]
        url = item.get("url") or ""
        revised = item.get("revised_prompt") or ""

        print(f"Result URL: {url}")
        print(f"URL path segments: {url.split('/') if url else 'N/A'}")
        print(f"URL contains /t2i/: {'/t2i/' in url}")
        print(f"URL contains /i2i/: {'/i2i/' in url}")
        print(f"Revised prompt: {revised[:200] if revised else '(none)'}")

        # Download the image to check if it's red (matching test image)
        if url:
            async with _no_proxy_client(timeout=60) as dl_client:
                img_resp = await dl_client.get(url)
                if img_resp.status_code == 200:
                    result_img = Image.open(io.BytesIO(img_resp.content))
                    # Check if the result has any red pixels (matching the test image)
                    colors = result_img.getcolors(maxcolors=100000)
                    if colors:
                        red_pixels = sum(count for count, color in colors if color[0] > 200 and color[1] < 100 and color[2] < 100)
                        total_pixels = sum(count for count, _ in colors)
                        red_pct = (red_pixels / total_pixels * 100) if total_pixels > 0 else 0
                        print(f"Result image: {result_img.size}, mode={result_img.mode}")
                        print(f"Red pixel ratio: {red_pct:.1f}% (test image is 100% red)")
                        if red_pct > 30:
                            print(">>> RESULT LIKELY USED ORIGINAL IMAGE (high red ratio)")
                        else:
                            print(">>> RESULT LIKELY IGNORED ORIGINAL IMAGE (low red ratio)")
                else:
                    print(f"Download failed: {img_resp.status_code}")

    return data


async def main():
    print("Agnes Image API img2img Diagnostic")
    print(f"API URL: {IMAGE_CREATE_URL}")
    print(f"Model: {IMAGE_MODEL}")
    print(f"API Key: {AGNES_API_KEY[:8]}...{AGNES_API_KEY[-4:]}")

    test_image_uri = create_test_image()

    # Test 1: txt2img (no image) — baseline
    body_txt2img = {
        "model": IMAGE_MODEL,
        "prompt": "A bright red square with white text saying TEST IMG2IMG",
        "size": "1024x1024",
    }

    # Test 2: img2img with enhancement prompt (like reference project)
    body_img2img_enhance = {
        "model": IMAGE_MODEL,
        "prompt": "img2img enhancement: upscale and sharpen this exact image. Keep the same subject, composition, colors, and layout — do NOT generate new content.",
        "size": "1024x1024",
        "image": [test_image_uri],
    }

    # Test 3: img2img with user-style prompt
    body_img2img_user = {
        "model": IMAGE_MODEL,
        "prompt": "保留原图的构图和颜色,不要生成新内容",
        "size": "1024x1024",
        "image": [test_image_uri],
    }

    # Run tests sequentially (to avoid rate limiting)
    results = []
    results.append(await test_request("txt2img (baseline, no image)", body_txt2img))

    print("\nWaiting 5s before next test...")
    await asyncio.sleep(5)

    results.append(await test_request("img2img + enhancement prompt", body_img2img_enhance))

    print("\nWaiting 5s before next test...")
    await asyncio.sleep(5)

    results.append(await test_request("img2img + user-style prompt", body_img2img_user))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    labels = ["txt2img baseline", "img2img + enhance prompt", "img2img + user prompt"]
    for i, (label, result) in enumerate(zip(labels, results)):
        if isinstance(result.get("data"), list) and len(result["data"]) > 0:
            url = result["data"][0].get("url", "")
            has_t2i = "/t2i/" in url
            has_i2i = "/i2i/" in url
            print(f"Test {i+1} ({label}): t2i={has_t2i}, i2i={has_i2i}, url={url[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
