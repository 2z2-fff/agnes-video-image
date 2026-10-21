"""Probe v2 — handles video_queue_full with long retry, answers the open questions.

Q1: Does the 2.5 video API accept a data-URI first_frame (no public URL needed)?
Q2: What is the exact completed-response shape (url field) for 2.5 Flash?

Free model only (agnes-video-2.5-flash, $0/s).
"""

import json
import os
import time

import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

KEY = os.environ["AGNES_API_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
CREATE = "https://apihub.agnes-ai.com/v1/videos"
QUERY = "https://apihub.agnes-ai.com/agnesapi"
MODEL = "agnes-video-2.5-flash"
C = httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=120)


def create_with_retry(body, max_wait=1500, label=""):
    """Retry on video_queue_full (503) until accepted."""
    start = time.time()
    attempt = 0
    while time.time() - start < max_wait:
        attempt += 1
        r = C.post(CREATE, headers=H, json=body)
        if r.status_code == 200:
            print(f"  [{label}] accepted on attempt {attempt}: {r.text[:300]}")
            return r.json()
        code = ""
        try:
            code = r.json().get("code", "")
        except Exception:
            pass
        print(f"  [{label}] attempt {attempt}: HTTP {r.status_code} {code} (t+{int(time.time()-start)}s)")
        if r.status_code == 400:
            print(f"  [{label}] 400 body: {r.text[:400]}")
            return {"__error__": r.text}
        time.sleep(20)
    print(f"  [{label}] gave up after {int(time.time()-start)}s")
    return None


def poll(video_id, label, timeout=900):
    start = time.time()
    while time.time() - start < timeout:
        r = C.get(QUERY, params={"video_id": video_id, "model_name": MODEL}, headers=H)
        if r.status_code != 200:
            print(f"  [{label}] query HTTP {r.status_code}: {r.text[:300]}")
            return None
        d = r.json()
        print(f"  [{label}] t+{int(time.time()-start):>3}s status={d.get('status')} progress={d.get('progress')}")
        if d.get("status") in ("completed", "failed"):
            print(f"  [{label}] FINAL: {json.dumps(d, ensure_ascii=False)[:900]}")
            return d
        time.sleep(6)
    print(f"  [{label}] TIMEOUT")
    return None


def png_data_uri(color=(90, 160, 230), size=(512, 512)):
    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


print("=== Q1: keyframe + DATA URI first_frame ===")
d = create_with_retry(
    {
        "model": MODEL,
        "prompt": "Slow camera push-in, the scene gently comes alive with soft light shimmer",
        "mode": "keyframe",
        "seconds": "4",
        "size": "720P",
        "aspect_ratio": "16:9",
        "first_frame": png_data_uri(),
    },
    label="keyframe-datauri",
)
if d and "video_id" in d:
    poll(d["video_id"], "keyframe-datauri")
elif d and "__error__" in d:
    print("  -> data URI REJECTED for first_frame (needs public URL)")

print("\n=== Q2: text mode, full response shape ===")
d2 = create_with_retry(
    {
        "model": MODEL,
        "prompt": "A paper plane gliding over a calm blue ocean at sunrise, slow cinematic pan",
        "mode": "text",
        "seconds": "4",
        "size": "720P",
        "aspect_ratio": "16:9",
    },
    label="text",
)
if d2 and "video_id" in d2:
    f = poll(d2["video_id"], "text")
    if f and f.get("url"):
        u = f["url"]
        h = C.head(u)
        print(f"  -> HEAD {h.status_code} type={h.headers.get('content-type')} len={h.headers.get('content-length')} host={u.split('/')[2]}")
