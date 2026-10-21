"""Live probe of the Agnes API — establishes ground truth before fixing the app.

Run: python scripts/probe_api.py
Prints a compact PASS/FAIL line per probe. Free models only (video 2.5 Flash = $0, images = $0).
"""

import base64
import io
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

KEY = os.environ["AGNES_API_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
VIDEO_CREATE = "https://apihub.agnes-ai.com/v1/videos"
VIDEO_QUERY = "https://apihub.agnes-ai.com/agnesapi"
IMAGE_CREATE = "https://apihub.agnes-ai.com/v1/images/generations"

# bypass system proxy: needed for this machine
CLIENT = httpx.Client(transport=httpx.AsyncHTTPTransport and httpx.HTTPTransport(proxy=None), timeout=120)


def show(label, resp):
    body = resp.text[:400]
    print(f"  HTTP {resp.status_code} | {label}\n    {body}")


def png_data_uri(color=(120, 180, 240), size=(256, 256)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def probe_old_params_rejected():
    """v2.0-style params must now be rejected by 2.5."""
    print("\n[1] v2.0-style params against agnes-video-2.5-flash (expect 400)")
    body = {
        "model": "agnes-video-2.5-flash",
        "prompt": "test",
        "width": 1152,
        "height": 648,
        "num_frames": 121,
        "frame_rate": 24,
    }
    r = CLIENT.post(VIDEO_CREATE, headers=H, json=body)
    show("width/height/num_frames", r)
    return r.status_code


def probe_image():
    """Image: tier + ratio on the 2.5 Flash image model."""
    print("\n[2] image txt2img agnes-image-2.5-flash 1K 1:1 (expect 200 + data[0].url)")
    body = {
        "model": "agnes-image-2.5-flash",
        "prompt": "A minimal blue circle centered on a white background, flat vector, high detail",
        "size": "1K",
        "ratio": "1:1",
        "extra_body": {"response_format": "url"},
    }
    r = CLIENT.post(IMAGE_CREATE, headers=H, json=body)
    show("image t2i", r)
    if r.status_code == 200:
        d = r.json()
        url = (d.get("data") or [{}])[0].get("url")
        print(f"    -> url={str(url)[:110]}")
        if url:
            g = CLIENT.get(url)
            print(f"    -> download: HTTP {g.status_code}, {len(g.content)} bytes, {g.headers.get('content-type')}")
        return url
    return None


def probe_image_old_size():
    """Old exact-4K size (3840x2160) — documented as 'accepted but may be normalized'."""
    print("\n[3] image with legacy exact size 3840x2160 (what the app currently sends)")
    body = {
        "model": "agnes-image-2.1-flash",
        "prompt": "A minimal red square centered on a white background, flat vector",
        "size": "3840x2160",
        "extra_body": {"response_format": "url"},
    }
    r = CLIENT.post(IMAGE_CREATE, headers=H, json=body)
    show("legacy size", r)
    if r.status_code == 200:
        url = (r.json().get("data") or [{}])[0].get("url")
        print(f"    -> url={str(url)[:110]}")


def video_create(model, extra):
    body = {"model": model, "seconds": "4", "size": "720P", "aspect_ratio": "16:9"}
    body.update(extra)
    return CLIENT.post(VIDEO_CREATE, headers=H, json=body)


def probe_video_text():
    print("\n[4] video text-mode agnes-video-2.5-flash (expect 200 + video_id)")
    r = video_create(
        "agnes-video-2.5-flash",
        {"prompt": "A paper plane gliding over a calm blue ocean at sunrise, slow cinematic camera pan", "mode": "text"},
    )
    show("video text create", r)
    if r.status_code != 200:
        return None
    d = r.json()
    print(f"    -> keys={list(d.keys())} video_id={d.get('video_id')}")
    return d.get("video_id")


def probe_video_keyframe_data_uri():
    """Can first_frame be a data URI, or does it require a public URL?"""
    print("\n[5] video keyframe with DATA URI first_frame (open question: doc says public URL)")
    r = video_create(
        "agnes-video-2.5-flash",
        {
            "prompt": "The camera slowly pushes in while the image subtly comes alive with gentle light shimmer",
            "mode": "keyframe",
            "first_frame": png_data_uri(),
        },
    )
    show("keyframe data-uri", r)
    return r.json().get("video_id") if r.status_code == 200 else None


def poll(video_id, model, label, timeout=600):
    print(f"\n[6] polling {label} video_id={video_id} (model_name={model})")
    start = time.time()
    while time.time() - start < timeout:
        r = CLIENT.get(VIDEO_QUERY, params={"video_id": video_id, "model_name": model}, headers=H)
        if r.status_code != 200:
            show("query", r)
            return None
        d = r.json()
        st = d.get("status")
        print(f"    t+{int(time.time()-start):>3}s status={st} progress={d.get('progress')}")
        if st in ("completed", "failed"):
            print(f"    full-ish: {json.dumps({k: d.get(k) for k in ('status','progress','seconds','size','url','error')}, ensure_ascii=False)[:500]}")
            return d
        time.sleep(5)
    print("    TIMEOUT")
    return None


def probe_query_without_model_name(video_id):
    print("\n[7] query keyframe task WITHOUT model_name (doc: only text mode may omit)")
    r = CLIENT.get(VIDEO_QUERY, params={"video_id": video_id}, headers=H)
    show("query no model_name", r)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "fast"):
        probe_old_params_rejected()
        probe_image()
        probe_image_old_size()
    if only in ("all", "video"):
        vid = probe_video_text()
        kf = probe_video_keyframe_data_uri()
        if vid:
            final = poll(vid, "agnes-video-2.5-flash", "text")
            if final and final.get("status") == "completed" and final.get("url"):
                u = final["url"]
                h = CLIENT.head(u)
                print(f"    -> HEAD {h.status_code} content-type={h.headers.get('content-type')} len={h.headers.get('content-length')}")
        if kf:
            poll(kf, "agnes-video-2.5-flash", "keyframe-data-uri")
            probe_query_without_model_name(kf)
        elif vid:
            probe_query_without_model_name(vid)
