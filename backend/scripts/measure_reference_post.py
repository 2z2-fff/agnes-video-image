"""Diagnose the 30s POST timeout on multi-image reference requests.

Measures:
  1. backend PNG re-encode cost per image (runs on the event loop today)
  2. end-to-end POST /api/generate latency with N reference images
"""

import base64
import io
import json
import sys
import time

import httpx
from PIL import Image

BASE = "http://127.0.0.1:8000"
C = httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=120)


def png_b64(size, color):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    from app.services.agnes_image import _ensure_png_data_uri

    # Photo-scale images: this is the case that blew past the 30s POST timeout.
    imgs = [png_b64((3000, 4000), (i * 60, 40, 90)) for i in range(2)]

    t0 = time.perf_counter()
    encoded = [_ensure_png_data_uri(im, max_side=1536) for im in imgs]
    conv = time.perf_counter() - t0
    print(
        f"[1] 2 张 3000x4000 图，降采样 1536px + PNG 编码: {conv:.2f}s, "
        f"单张 base64 ≈ {len(encoded[0]) / 1024 / 1024:.1f} MB"
    )

    # [2] end-to-end POST with 2 reference images
    payload = {
        "mode": "reference",
        "prompt": "Use <Picture 1> as the subject and <Picture 2> as the environment",
        "images": encoded,
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
    }
    body = json.dumps(payload)
    print(f"[2] POST 请求体大小 ≈ {len(body) / 1024 / 1024:.1f} MB")

    for attempt in range(1, 4):
        t0 = time.perf_counter()
        try:
            r = C.post(f"{BASE}/api/generate", content=body, headers={"Content-Type": "application/json"})
            dt = time.perf_counter() - t0
            print(f"    attempt {attempt}: HTTP {r.status_code} in {dt:.2f}s -> {r.text[:160]}")
            if r.status_code in (200, 202):
                break
        except httpx.TimeoutException as e:
            dt = time.perf_counter() - t0
            print(f"    attempt {attempt}: TIMEOUT after {dt:.2f}s ({type(e).__name__})")
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
