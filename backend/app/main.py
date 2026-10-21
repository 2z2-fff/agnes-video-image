"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    BACKEND_PORT,
    CORS_ORIGINS,
    FLASH_VIDEO_SIZES,
    IMAGE_MODEL,
    IMAGE_RATIO_LABELS,
    IMAGE_RATIOS,
    IMAGE_SIZE_LABELS,
    IMAGE_SIZES,
    UPLOADS_DIR,
    VIDEO_ASPECT_RATIOS,
    VIDEO_MAX_SECONDS,
    VIDEO_MIN_SECONDS,
    VIDEO_MODEL,
    VIDEO_SIZES,
)
from app.api.video import router as video_router
from app.api.image import router as image_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agnes AI Generator",
    description="Video & image generation powered by Agnes AI APIs",
    version="2.0.0",
)

# CORS: allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(video_router)
app.include_router(image_router)

# Serve uploaded images as static files
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "agnes-video-generator"}


@app.get("/api/health")
async def health():
    """API health check."""
    return {"status": "ok"}


@app.get("/api/config")
async def config():
    """Expose the active models and the values they actually accept.

    The frontend uses this to only offer combinations the API will accept
    (e.g. agnes-video-2.5-flash rejects anything but 720P).
    """
    is_flash = VIDEO_MODEL.endswith("flash")
    return {
        "video": {
            "model": VIDEO_MODEL,
            "sizes": list(FLASH_VIDEO_SIZES if is_flash else VIDEO_SIZES),
            "aspect_ratios": list(VIDEO_ASPECT_RATIOS),
            "min_seconds": VIDEO_MIN_SECONDS,
            "max_seconds": VIDEO_MAX_SECONDS,
        },
        "image": {
            "model": IMAGE_MODEL,
            "sizes": list(IMAGE_SIZES),
            "ratios": list(IMAGE_RATIOS),
            "size_labels": IMAGE_SIZE_LABELS,
            "ratio_labels": IMAGE_RATIO_LABELS,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        reload=True,
    )
