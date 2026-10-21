"""Realistic reproduction: reference-mode submit with photo-scale images.

Sends 2 noise JPEGs (3000x4000, ~9MB each — what a phone photo looks like) the
way the browser would (raw base64), and measures the POST. This is the case
that produced "timeout of 30000ms exceeded".
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


def photo_b64(seed: int) -> str:
    img = Image.effect_noise((3000, 4000), 60 + seed).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()


def main():
    print("[1] 构造 2 张 3000x4000 照片级图片…")
    imgs = [photo_b64(i) for i in range(2)]
    print(f"    浏览器侧原始 base64: {sum(len(i) for i in imgs) / 1024 / 1024:.1f} MB")

    payload = {
        "mode": "reference",
        "prompt": "Use <Picture 1> as the main character and <Picture 2> as the scene, cinematic",
        "images": imgs,
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
    }
    body = json.dumps(payload)
    print(f"[2] POST body: {len(body) / 1024 / 1024:.1f} MB")

    t0 = time.perf_counter()
    try:
        r = C.post(f"{BASE}/api/generate", content=body, headers={"Content-Type": "application/json"})
        dt = time.perf_counter() - t0
        print(f"[3] HTTP {r.status_code} in {dt:.2f}s")
        print(f"    {r.text[:240]}")
        if r.status_code == 202:
            job_id = r.json()["job_id"]
            print("[4] 202 → 后台排队，检查 job 可查")
            for _ in range(3):
                time.sleep(3)
                j = C.get(f"{BASE}/api/jobs/{job_id}").json()
                print(f"    job status={j.get('status')} task_id={j.get('task_id')}")
                if j.get("task_id"):
                    break
    except httpx.TimeoutException as e:
        dt = time.perf_counter() - t0
        print(f"[3] TIMEOUT after {dt:.2f}s ({type(e).__name__})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
