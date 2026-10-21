"""Diagnose the image API 503: print the raw error body for t2i and i2i."""

import base64
import io
import os

import httpx
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

KEY = os.environ["AGNES_API_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
URL = "https://apihub.agnes-ai.com/v1/images/generations"
C = httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=120)


def png_uri():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (512, 288), (40, 90, 160)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


print("[t2i 1K]")
r = C.post(URL, headers=H, json={
    "model": "agnes-image-2.5-flash",
    "prompt": "A calm blue ocean at sunrise, cinematic",
    "size": "1K",
    "ratio": "16:9",
    "extra_body": {"response_format": "url"},
})
print(r.status_code, r.text[:300])

print("\n[i2i 1K data-uri]")
r = C.post(URL, headers=H, json={
    "model": "agnes-image-2.5-flash",
    "prompt": "Make the scene a neon cyberpunk night, keep composition",
    "size": "1K",
    "ratio": "16:9",
    "extra_body": {"image": [png_uri()], "response_format": "url"},
})
print(r.status_code, r.text[:400])

print("\n[i2i with legacy exact size]")
r = C.post(URL, headers=H, json={
    "model": "agnes-image-2.5-flash",
    "prompt": "Make the scene a neon cyberpunk night, keep composition",
    "size": "1024x768",
    "extra_body": {"image": [png_uri()], "response_format": "url"},
})
print(r.status_code, r.text[:400])
