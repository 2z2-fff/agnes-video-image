"""Diagnostic script: test Agnes Video API img2vid with different parameter placements.

Tests multiple approaches to find which one the LiteLLM proxy accepts:
1. txt2vid (baseline, no image)
2. Top-level image as pure base64 (old approach, suspected to fail)
3. extra_body.image as array of data URIs (new approach, same as img2img fix)

NOTE: Agnes API allows only 1 concurrent task. Tests run sequentially with delays.
"""

import asyncio
import base64
import io
import json
import os
import sys
import time

import httpx
from PIL import Image

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = "https://apihub.agnes-ai.com"
CREATE_VIDEO_URL = f"{AGNES_BASE_URL}/v1/videos"
AGNES_MODEL = "agnes-video-v2.0"


def _no_proxy_client(**kwargs):
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport, **kwargs)


def _get_headers():
    return {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }


def create_test_image() -> str:
    """Create a small 100x100 red PNG image and return as data URI."""
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


async def test_approach(name: str, body: dict, delay: float = 20.0):
    """Test a single approach and log the result."""
    print(f"\n{'='*60}")
    print(f"Test: {name}")
    print(f"Body keys: {list(body.keys())}")
    if "extra_body" in body:
        print(f"  extra_body keys: {list(body['extra_body'].keys())}")
        if "image" in body["extra_body"]:
            img_val = body["extra_body"]["image"]
            if isinstance(img_val, list):
                print(f"  extra_body.image: array of {len(img_val)} items, first item len={len(img_val[0]) if img_val else 0}")
            else:
                print(f"  extra_body.image: string, len={len(str(img_val))}")
    if "image" in body:
        print(f"  top-level image: string, len={len(str(body['image']))}")
    print(f"{'='*60}")

    try:
        async with _no_proxy_client(timeout=120) as client:
            resp = await client.post(
                CREATE_VIDEO_URL,
                headers=_get_headers(),
                json=body,
            )

        print(f"Status: {resp.status_code}")

        try:
            data = resp.json()
            print(f"Response keys: {list(data.keys())}")
            print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")

            # Check for task ID
            for key in ("video_id", "id", "task_id"):
                if data.get(key):
                    print(f"Task ID ({key}): {data[key]}")
                    return data[key]
        except Exception:
            print(f"Response text: {resp.text[:500]}")

        return None

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return None


async def main():
    if not AGNES_API_KEY:
        print("ERROR: AGNES_API_KEY not set in .env")
        return

    print(f"API Key: {AGNES_API_KEY[:10]}...{AGNES_API_KEY[-4:]}")
    print(f"Endpoint: {CREATE_VIDEO_URL}")
    print(f"Model: {AGNES_MODEL}")

    # Create a small test image
    data_uri = create_test_image()
    pure_b64 = data_uri.split(",")[1]
    print(f"\nTest image: 100x100 red PNG, data_uri_len={len(data_uri)}, b64_len={len(pure_b64)}")

    # Common parameters for all tests
    common = {
        "model": AGNES_MODEL,
        "prompt": "A red square slowly pulsing, cinematic lighting",
        "width": 1152,
        "height": 648,
        "num_frames": 41,  # 8*5+1 = 41, ~1.7s @ 24fps (short for testing)
        "frame_rate": 24,
    }

    results = {}

    # Test 1: txt2vid (baseline)
    body1 = dict(common)
    task_id = await test_approach("txt2vid (baseline, no image)", body1, delay=0)
    results["txt2vid"] = task_id

    if task_id:
        print(f"\n>>> txt2vid succeeded! Task ID: {task_id}")
        print(">>> Waiting 20s before next test (API allows only 1 concurrent task)...")
        await asyncio.sleep(20)

    # Test 2: Top-level image as pure base64 (old approach)
    body2 = dict(common)
    body2["image"] = pure_b64
    task_id = await test_approach("img2vid top-level image (pure base64, old approach)", body2, delay=0)
    results["top_level_b64"] = task_id

    if task_id:
        print(f"\n>>> Top-level base64 succeeded! Task ID: {task_id}")
    else:
        print(f"\n>>> Top-level base64 FAILED (expected if LiteLLM strips it)")

    print(">>> Waiting 20s before next test...")
    await asyncio.sleep(20)

    # Test 3: extra_body.image as array of data URIs (new approach)
    body3 = dict(common)
    body3["extra_body"] = {
        "image": [data_uri],
    }
    task_id = await test_approach("img2vid extra_body.image (data URI array, new approach)", body3, delay=0)
    results["extra_body_data_uri"] = task_id

    if task_id:
        print(f"\n>>> extra_body.image data URI succeeded! Task ID: {task_id}")
    else:
        print(f"\n>>> extra_body.image data URI FAILED")

    print(">>> Waiting 20s before next test...")
    await asyncio.sleep(20)

    # Test 4: extra_body.image as array of pure base64 (no data URI prefix)
    body4 = dict(common)
    body4["extra_body"] = {
        "image": [pure_b64],
    }
    task_id = await test_approach("img2vid extra_body.image (pure base64 array)", body4, delay=0)
    results["extra_body_pure_b64"] = task_id

    if task_id:
        print(f"\n>>> extra_body.image pure base64 succeeded! Task ID: {task_id}")
    else:
        print(f"\n>>> extra_body.image pure base64 FAILED")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, task_id in results.items():
        status = f"OK (task_id={task_id})" if task_id else "FAILED"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
