"""Investigate the permanently-full video queue.

Questions:
  1. Is the submit rejection really `video_queue_full` right now?
  2. Does the API expose a task list (so we can find a stuck task holding the
     single concurrency slot)?
  3. Can a stuck task be cancelled?
"""

import os

import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

KEY = os.environ["AGNES_API_KEY"]
BASE = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com").rstrip("/")
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
C = httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=60)
MODEL = "agnes-video-2.5-flash"


def show(tag, resp, limit=400):
    print(f"\n[{tag}] HTTP {resp.status_code}")
    print("   ", resp.text[:limit].replace("\n", " "))


print("=== 1) 当前提交是否仍是 video_queue_full ===")
r = C.post(f"{BASE}/v1/videos", headers=H, json={
    "model": MODEL, "prompt": "queue probe", "mode": "text",
    "seconds": "4", "size": "720P", "aspect_ratio": "16:9",
})
show("POST /v1/videos", r)

print("\n=== 2) 是否存在任务列表接口 ===")
for path in ["/v1/videos", "/v1/videos?limit=20", f"/agnesapi?model_name={MODEL}"]:
    try:
        r = C.get(f"{BASE}{path}", headers=H)
        show(f"GET {path}", r, 800)
    except Exception as e:
        print(f"\n[GET {path}] ERROR {type(e).__name__}: {e}")

print("\n=== 3) 已知任务当前状态（是否还占着并发位） ===")
for tid in [
    "task_vzuHpceX730CvA4wfB5ma2NRb3Qecvo4",
    "task_vzDZyOizcFszHDbgOwhR6HByXwRZMJ7q",
    "task_mglLKENzGFzH1Dmaqu8bE06A1xE9WtEW",
    "task_dNIeD73kEnCsuYDbbBQ0xCLlA8av9R9Y",
]:
    try:
        r = C.get(f"{BASE}/agnesapi", headers=H, params={"video_id": tid, "model_name": MODEL})
        if r.status_code == 200:
            d = r.json()
            print(f"  {tid[-12:]}: status={d.get('status')} progress={d.get('progress')}")
        else:
            print(f"  {tid[-12:]}: HTTP {r.status_code} {r.text[:120]}")
    except Exception as e:
        print(f"  {tid[-12:]}: ERROR {type(e).__name__}")
