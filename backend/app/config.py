"""Application configuration loaded from environment variables.

All values are aligned with the official Agnes AI docs
(https://agnes-ai.com/zh-Hans/docs/) as of the Video 2.5 / Image 2.5 generation.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ─── Agnes API ────────────────────────────────────────────────────
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com")

# ─── Video (Agnes Video 2.5 family) ───────────────────────────────
# Model IDs documented today: agnes-video-2.5 (paid) and
# agnes-video-2.5-flash (currently $0/s, 720P only).
VIDEO_MODEL = os.getenv("AGNES_VIDEO_MODEL", "agnes-video-2.5-flash")

CREATE_VIDEO_URL = f"{AGNES_BASE_URL}/v1/videos"
QUERY_VIDEO_URL = f"{AGNES_BASE_URL}/agnesapi"

# `size` tiers. Flash accepts only "720P" and returns 400 for anything else.
VIDEO_SIZES = ("720P", "1080P", "1K", "2K")
FLASH_VIDEO_SIZES = ("720P",)

# Supported `aspect_ratio` values (whitelist — "auto" and pixel strings are rejected).
VIDEO_ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")

# `seconds` must be a string "4"–"12".
VIDEO_MIN_SECONDS = 4
VIDEO_MAX_SECONDS = 12

# Reference-media limits (agnes-video-2.5)
VIDEO_MAX_IMAGES = 8          # mode="reference", agnes-video-2.5
FLASH_MAX_IMAGES = 5          # mode="reference", agnes-video-2.5-flash
VIDEO_MAX_AUDIOS = 3
VIDEO_MAX_VIDEOS = 1
VIDEO_MAX_REFERENCE_FILES = 12


def max_reference_images(model: str | None = None) -> int:
    """How many `images` the given model accepts in `reference` mode."""
    target = model or VIDEO_MODEL
    return FLASH_MAX_IMAGES if target.endswith("flash") else VIDEO_MAX_IMAGES

# Polling: docs recommend every 1–2s until completed/failed.
POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 900

# ─── Image (Agnes Image 2.5 Flash) ────────────────────────────────
IMAGE_CREATE_URL = f"{AGNES_BASE_URL}/v1/images/generations"
IMAGE_MODEL = os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.5-flash")

# Tier-based `size` + `ratio`. Exact pixel sizes are accepted but silently
# normalized, so we only ever send tiers.
IMAGE_SIZES = ("1K", "2K", "3K", "4K")
IMAGE_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9")

# Human-readable labels for the UI
IMAGE_SIZE_LABELS: dict[str, str] = {
    "1K": "1K 标准",
    "2K": "2K 高清",
    "3K": "3K 超清",
    "4K": "4K 最高",
}
IMAGE_RATIO_LABELS: dict[str, str] = {
    "1:1": "1:1 方形",
    "16:9": "16:9 横屏",
    "9:16": "9:16 竖屏",
    "4:3": "4:3 横版",
    "3:4": "3:4 竖版",
    "3:2": "3:2 横版",
    "2:3": "2:3 竖版",
    "21:9": "21:9 超宽",
}

# Retry / backoff behaviour.
# The provider rejects requests with 503 "queue is full" while capacity is
# exhausted; these waits are free (no task is created), so allow a generous budget.
IMAGE_MAX_RETRIES = 8
IMAGE_RATE_LIMIT_COOLD = 20.0
IMAGE_SERVICE_UNAVAIL_COOLD = 20.0
IMAGE_NETWORK_RETRY_DELAYS = [10, 20, 30]

# ─── Server ───────────────────────────────────────────────────────
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# Uploads directory for storing generated images.
# Override with UPLOADS_DIR when the default location is not writable
# (restricted sandbox, read-only container volume, etc.).
UPLOADS_DIR = Path(
    os.getenv("UPLOADS_DIR") or (Path(__file__).parent.parent / "uploads")
).resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
