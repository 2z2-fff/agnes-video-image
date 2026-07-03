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
