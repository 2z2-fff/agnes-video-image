"""End-to-end test against the running backend (http://127.0.0.1:8000).

Verifies the real user paths:
  A. image-to-image  (POST /api/image/generate, mode=img2img)
  B. text-to-video   (POST /api/generate, mode=txt2vid)
  C. image-to-video  (POST /api/generate, mode=img2vid, keyframe + PNG data URI)

The provider's queues are shared and often full, so each phase retries
patiently. Exit code 0 = everything passed.
"""

import base64
import io
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
# Generous client timeout: the /wait endpoint long-polls server-side, and
# generation itself can take minutes once the queue frees up.
C = httpx.Client(timeout=200)

results: list[tuple[str, bool, str]] = []


def png_b64(w=768, h=432):
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), (30, 70, 130))
    # add a gradient so the model has something structured to animate
    px = img.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (30 + x % 200, 70 + y % 120, 130)
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def wait_task(task_id, label, timeout=1800):
    """Long-poll through our own backend endpoint."""
    start = time.time()
    last_status = "unknown"
    while time.time() - start < timeout:
        try:
            r = C.get(f"{BASE}/api/generate/{task_id}/wait", params={"timeout": 120})
            if r.status_code == 200:
                d = r.json()
                st = d.get("status")
                if st != last_status:
                    print(f"    [{label}] status -> {st} (progress={d.get('progress')})")
                    last_status = st
                if st in ("completed", "failed", "timeout"):
                    print(f"    [{label}] FINAL: {st} url={d.get('video_url')}")
                    return d
            else:
                print(f"    [{label}] wait HTTP {r.status_code}: {r.text[:200]}")
        except httpx.TransportError as e:
            print(f"    [{label}] transport {type(e).__name__}, retrying")
        time.sleep(5)
    print(f"    [{label}] client-side timeout after {timeout}s")
    return {"status": "timeout", "error": "client-side timeout"}


def resolve_job(job_id, label, timeout=1200):
    """A 202 means the backend is retrying a full queue in the background."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = C.get(f"{BASE}/api/jobs/{job_id}", timeout=60)
            if r.status_code == 200:
                j = r.json()
                st = j.get("status")
                print(f"    [{label}] job {st} task_id={j.get('task_id')}")
                if j.get("task_id"):
                    return {"task_id": j["task_id"]}
                if st in ("failed", "timeout"):
                    return {"__fatal__": j.get("error") or st}
        except httpx.TransportError as e:
            print(f"    [{label}] job poll transport {type(e).__name__}")
        time.sleep(5)
    return {"__fatal__": "job never produced a task id"}


def create_video(payload, label, max_wait=1800):
    """POST /api/generate, tolerating queue-full (202 job) and transient errors."""
    start = time.time()
    attempt = 0
    while time.time() - start < max_wait:
        attempt += 1
        try:
            r = C.post(f"{BASE}/api/generate", json=payload, timeout=120)
        except httpx.TransportError as e:
            print(f"    [{label}] transport {type(e).__name__} on create")
            time.sleep(10)
            continue
        if r.status_code == 200:
            d = r.json()
            print(f"    [{label}] created after {attempt} attempt(s): {d}")
            return d
        if r.status_code == 202:
            d = r.json()
            print(f"    [{label}] queued as job {d.get('job_id')} (queue full), waiting...")
            return resolve_job(d["job_id"], label)
        print(f"    [{label}] attempt {attempt}: HTTP {r.status_code} {r.text[:200]}")
        if r.status_code in (400, 422):
            return {"__fatal__": r.text}
        time.sleep(20)
    return None


# ─── A. image-to-image ────────────────────────────────────────────
def phase_image():
    print("\n[A] image-to-image (agnes-image-2.5-flash, 1K, 16:9)")
    payload = {
        "mode": "img2img",
        "prompt": "Turn the scene into a rain-soaked cyberpunk night with neon reflections, preserve the composition",
        "image": png_b64(),
        "size": "1K",
        "ratio": "16:9",
    }
    start = time.time()
    attempt = 0
    while time.time() - start < 900:
        attempt += 1
        try:
            r = C.post(f"{BASE}/api/image/generate", json=payload, timeout=600)
        except httpx.TransportError as e:
            print(f"    [i2i] transport {type(e).__name__}")
            time.sleep(10)
            continue
        if r.status_code == 200:
            d = r.json()
            url = d.get("image_url", "")
            print(f"    [i2i] OK after {attempt} attempt(s): {url}")
            # verify the file is served and is a real PNG
            img = C.get(f"{BASE}{url}")
            ok = img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
            results.append(("image-to-image", ok, f"{url} bytes={len(img.content)}"))
            return
        print(f"    [i2i] attempt {attempt}: HTTP {r.status_code} {r.text[:160]}")
        time.sleep(20)
    results.append(("image-to-image", False, "queue never freed within 900s"))


# ─── B. text-to-video ─────────────────────────────────────────────
def phase_txt2vid():
    print("\n[B] text-to-video (agnes-video-2.5-flash, 4s, 720P, 16:9)")
    payload = {
        "mode": "txt2vid",
        "prompt": "A paper plane gliding over a calm blue ocean at sunrise, slow cinematic pan",
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
        "seed": 1234,
    }
    d = create_video(payload, "txt2vid")
    if not d or "__fatal__" in d:
        results.append(("text-to-video", False, str(d)[:200]))
        return None
    final = wait_task(d["task_id"], "txt2vid")
    if final.get("status") != "completed":
        results.append(("text-to-video", False, str(final.get("error"))[:200]))
        return None
    # verify stream + download endpoints
    st = C.get(f"{BASE}/api/generate/{d['task_id']}/stream", headers={"Range": "bytes=0-1023"})
    dl = C.get(f"{BASE}/api/generate/{d['task_id']}/download")
    ok = st.status_code in (200, 206) and dl.status_code == 200 and len(dl.content) > 10_000
    results.append((
        "text-to-video",
        ok,
        f"url={final.get('video_url')} range={st.status_code}/{len(st.content)}B download={dl.status_code}/{len(dl.content)}B",
    ))


# ─── C. image-to-video ────────────────────────────────────────────
def phase_img2vid():
    print("\n[C] image-to-video (keyframe + PNG data URI)")
    payload = {
        "mode": "img2vid",
        "prompt": "Camera slowly pushes in while the scene comes alive with soft light shimmer",
        "image": png_b64(),
        "aspect_ratio": "16:9",
        "seconds": 4,
        "size": "720P",
    }
    d = create_video(payload, "img2vid")
    if not d or "__fatal__" in d:
        results.append(("image-to-video", False, str(d)[:200]))
        return
    final = wait_task(d["task_id"], "img2vid")
    ok = final.get("status") == "completed" and bool(final.get("video_url"))
    results.append(("image-to-video", ok, f"url={final.get('video_url')}"))


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "image"):
        phase_image()
    if only in ("all", "video"):
        phase_txt2vid()
        phase_img2vid()

    print("\n===== SUMMARY =====")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    sys.exit(0 if results and all(ok for _, ok, _ in results) else 1)
