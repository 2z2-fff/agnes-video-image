"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

# Agnes API settings
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com")
AGNES_MODEL = os.getenv("AGNES_MODEL", "agnes-video-v2.0")

# Derived endpoints
CREATE_VIDEO_URL = f"{AGNES_BASE_URL}/v1/videos"
QUERY_VIDEO_URL = f"{AGNES_BASE_URL}/agnesapi"

# Server settings
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# Aspect ratio -> pixel resolution mapping
ASPECT_MAP: dict[str, tuple[int, int]] = {
    "16:9": (1152, 648),
    "9:16": (648, 1152),
    "1:1": (768, 768),
    "4:3": (960, 720),
}

# Default polling settings
POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 600

# ─── Agnes Image API ──────────────────────────────────────────────
IMAGE_CREATE_URL = f"{AGNES_BASE_URL}/v1/images/generations"
IMAGE_MODEL = os.getenv("AGNES_IMAGE_MODEL", "agnes-image-2.1-flash")

# Image size options (label for frontend display)
IMAGE_SIZE_MAP: dict[str, str] = {
    "1024x1024": "标准 1:1",
    "3840x2160": "4K 16:9",
    "2160x3840": "4K 9:16",
    "4096x4096": "4K 1:1",
}

# 4K tier rate limit: 1 request per 60 seconds
IMAGE_RATE_LIMIT_COOLD = 65.0
IMAGE_SERVICE_UNAVAIL_COOLD = 15.0  # seconds — queue full clears faster than rate limit
IMAGE_MAX_RETRIES = 3
IMAGE_NETWORK_RETRY_DELAYS = [10, 20, 30]  # seconds

# Uploads directory for storing generated images
from pathlib import Path
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
