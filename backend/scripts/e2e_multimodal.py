"""E2E test for the two new video modes: first/last frame and multi-image reference.

Phase 0 (fast, no queue): request validation.
Phase 1 (slow):  img2vid with BOTH first and last frame.
Phase 2 (slow):  reference with 2 images.

Run: python -u scripts/e2e_multimodal.py
Exit code 0 = all passed.
"""

import base64
import io
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
C = httpx.Client(timeout=200)
results: list[tuple[str, bool, str]] = []


def png(color, size=(640, 384), label=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    if label:
        d.rectangle([20, 20, size[0] - 20, size[1] - 20], outline=(255, 255, 255), width=6)
        d.text((40, 40), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def check(label, payload, expected_status):
    try:
        r = C.post(f"{BASE}/api/generate", json=payload, timeout=120)
        ok = r.status_code == expected_status
        detail = f"HTTP {r.status_code}"
        if not ok:
            detail += f" (expected {expected_status}) {r.text[:160]}"
        results.append((label, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    except Exception as e:
        results.append((label, False, str(e)[:120]))
        print(f"  [FAIL] {label}: {e}")


def wait_task(task_id, label, timeout=2400):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        try:
            r = C.get(f"{BASE}/api/generate/{task_id}", timeout=60)
            if r.status_code == 200:
                d = r.json()
                st = d.get("status")
                if st != last:
                    print(f"    [{label}] {st} progress={d.get('progress')}")
                    last = st
                if st in ("completed", "failed"):
                    return d
            else:
                print(f"    [{label}] query HTTP {r.status_code}")
        except httpx.TransportError as e:
            print(f"    [{label}] transport {type(e).__name__}, retrying")
        time.sleep(8)
    return {"status": "timeout"}


def create_and_wait(label, payload, max_create_wait=2400):
    start = time.time()
    attempt = 0
    while time.time() - start < max_create_wait:
        attempt += 1
        try:
            r = C.post(f"{BASE}/api/generate", json=payload, timeout=900)
        except httpx.TransportError as e:
            print(f"    [{label}] transport {type(e).__name__} on create")
            time.sleep(10)
            continue
        if r.status_code == 200:
            d = r.json()
            print(f"    [{label}] created after {attempt} attempt(s): {d['task_id']}")
            final = wait_task(d["task_id"], label)
            ok = final.get("status") == "completed" and bool(final.get("video_url"))
            results.append((label, ok, f"url={final.get('video_url')}"))
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {final.get('status')} {final.get('video_url')}")
            return
        print(f"    [{label}] attempt {attempt}: HTTP {r.status_code} {r.text[:130]}")
        if r.status_code in (400, 422):
            results.append((label, False, f"HTTP {r.status_code} {r.text[:160]}"))
            return
        time.sleep(20)
    results.append((label, False, "queue never freed"))
    print(f"  [FAIL] {label}: queue never freed")


print("=== Phase 0: validation (no queue consumed) ===")
# reference mode must reject keyframe media
check(
    "reference + first_frame 被拒绝",
    {"mode": "reference", "prompt": "x", "image": png((10, 10, 200)), "images": [png((200, 10, 10))]},
    422,
)
# txt2vid must reject images
check(
    "txt2vid + images 被拒绝",
    {"mode": "txt2vid", "prompt": "x", "images": [png((200, 10, 10))]},
    422,
)
# img2vid without an image
check("img2vid 缺首帧被拒绝", {"mode": "img2vid", "prompt": "x"}, 422)
# reference without images
check("reference 缺图片被拒绝", {"mode": "reference", "prompt": "x"}, 422)
# Flash caps reference images at 5 -> 6 images must be rejected by the service (400)
check(
    "reference 6 张（Flash 上限 5）被拒绝",
    {"mode": "reference", "prompt": "x", "images": [png((i * 30, 40, 90)) for i in range(6)]},
    400,
)

print("\n=== Phase 1: first + last frame (keyframe) ===")
create_and_wait(
    "首尾帧",
    {
        "mode": "img2vid",
        "prompt": "Smooth cinematic transition: the red studio scene gradually transforms "
                  "into the blue outdoor scene, camera slowly pushes in, natural pacing",
        "image": png((200, 40, 40), label="START"),
        "last_image": png((40, 80, 200), label="END"),
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
    },
)

print("\n=== Phase 2: multi-image reference ===")
create_and_wait(
    "多图参考(2张)",
    {
        "mode": "reference",
        "prompt": "Use <Picture 1> as the main character and <Picture 2> as the background "
                  "environment. The character walks through that environment, cinematic lighting",
        "images": [png((240, 200, 60), label="CHAR"), png((30, 120, 160), label="SCENE")],
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
    },
)

print("\n===== SUMMARY =====")
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
sys.exit(0 if results and all(ok for _, ok, _ in results) else 1)
