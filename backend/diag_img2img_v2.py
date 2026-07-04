"""Diagnostic script v2: test multiple approaches for Agnes Image API img2img.

Tests:
1. extra_body.image on /v1/images/generations
2. image on /v1/images/edits endpoint
3. multipart form-data on /v1/images/edits (OpenAI standard)
"""

import asyncio
import base64
import io
import os
import sys
import json
import httpx
from PIL import Image, ImageDraw

from dotenv import load_dotenv
load_dotenv()

AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com")
IMAGE_MODEL = "agnes-image-2.1-flash"

if not AGNES_API_KEY:
    print("ERROR: AGNES_API_KEY not set")
    sys.exit(1)


def _no_proxy_client(**kwargs) -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def create_test_image() -> bytes:
    """Create a distinctive test image, return raw PNG bytes."""
    img = Image.new("RGB", (256, 256), color=(255, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((30, 120), "TEST IMG2IMG", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def test_extra_body(png_bytes: bytes):
    """Test 1: extra_body.image on /v1/images/generations"""
    print(f"\n{'='*60}")
    print("TEST 1: extra_body.image on /v1/images/generations")
    print(f"{'='*60}")

    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"

    body = {
        "model": IMAGE_MODEL,
        "prompt": "img2img enhancement: keep the same subject and colors",
        "size": "1024x1024",
        "extra_body": {
            "image": [data_uri],
            "response_format": "url",
        },
    }

    async with _no_proxy_client(timeout=240) as client:
        resp = await client.post(
            f"{AGNES_BASE_URL}/v1/images/generations",
            headers=_get_headers(),
            json=body,
        )

    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("data"):
            url = data["data"][0].get("url", "")
            print(f"URL: {url[:100]}")
            print(f"Has /t2i/: {'/t2i/' in url}, Has /i2i/: {'/i2i/' in url}")
    else:
        print(f"Error: {resp.text[:500]}")


async def test_edits_json(png_bytes: bytes):
    """Test 2: image on /v1/images/edits endpoint (JSON body)"""
    print(f"\n{'='*60}")
    print("TEST 2: image on /v1/images/edits (JSON body)")
    print(f"{'='*60}")

    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"

    body = {
        "model": IMAGE_MODEL,
        "prompt": "img2img enhancement: keep the same subject and colors",
        "size": "1024x1024",
        "image": [data_uri],
    }

    async with _no_proxy_client(timeout=240) as client:
        resp = await client.post(
            f"{AGNES_BASE_URL}/v1/images/edits",
            headers=_get_headers(),
            json=body,
        )

    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("data"):
            url = data["data"][0].get("url", "")
            print(f"URL: {url[:100]}")
            print(f"Has /t2i/: {'/t2i/' in url}, Has /i2i/: {'/i2i/' in url}")
        print(f"Response keys: {list(data.keys())}")
    else:
        print(f"Error: {resp.text[:500]}")


async def test_edits_multipart(png_bytes: bytes):
    """Test 3: multipart form-data on /v1/images/edits (OpenAI standard)"""
    print(f"\n{'='*60}")
    print("TEST 3: multipart form-data on /v1/images/edits")
    print(f"{'='*60}")

    files = {
        "image": ("test.png", png_bytes, "image/png"),
    }
    data = {
        "model": IMAGE_MODEL,
        "prompt": "img2img enhancement: keep the same subject and colors",
        "size": "1024x1024",
    }

    headers = {"Authorization": f"Bearer {AGNES_API_KEY}"}

    async with _no_proxy_client(timeout=240) as client:
        resp = await client.post(
            f"{AGNES_BASE_URL}/v1/images/edits",
            headers=headers,
            files=files,
            data=data,
        )

    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        resp_data = resp.json()
        if resp_data.get("data"):
            url = resp_data["data"][0].get("url", "")
            print(f"URL: {url[:100]}")
            print(f"Has /t2i/: {'/t2i/' in url}, Has /i2i/: {'/i2i/' in url}")
        print(f"Response keys: {list(resp_data.keys())}")
    else:
        print(f"Error: {resp.text[:500]}")


async def test_generations_with_image_url(png_bytes: bytes):
    """Test 4: /v1/images/generations with image as public URL (not data URI)"""
    print(f"\n{'='*60}")
    print("TEST 4: image as bare base64 (no data URI prefix)")
    print(f"{'='*60}")

    b64 = base64.b64encode(png_bytes).decode("ascii")

    body = {
        "model": IMAGE_MODEL,
        "prompt": "img2img enhancement: keep the same subject and colors",
        "size": "1024x1024",
        "image": [b64],  # bare base64, no data URI prefix
    }

    async with _no_proxy_client(timeout=240) as client:
        resp = await client.post(
            f"{AGNES_BASE_URL}/v1/images/generations",
            headers=_get_headers(),
            json=body,
        )

    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("data"):
            url = data["data"][0].get("url", "")
            print(f"URL: {url[:100]}")
            print(f"Has /t2i/: {'/t2i/' in url}, Has /i2i/: {'/i2i/' in url}")
    else:
        print(f"Error: {resp.text[:500]}")


async def main():
    print("Agnes Image API img2img Diagnostic v2")
    print(f"API Key: {AGNES_API_KEY[:8]}...{AGNES_API_KEY[-4:]}")

    png_bytes = create_test_image()
    print(f"Test image: {len(png_bytes)} bytes PNG")

    await test_extra_body(png_bytes)
    await asyncio.sleep(3)

    await test_edits_json(png_bytes)
    await asyncio.sleep(3)

    await test_edits_multipart(png_bytes)
    await asyncio.sleep(3)

    await test_generations_with_image_url(png_bytes)

    print(f"\n{'='*60}")
    print("DONE - check which test returned /i2i/ in URL")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
