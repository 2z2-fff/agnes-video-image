"""Image generation REST endpoints."""

import logging
from fastapi import APIRouter

from app.schemas import ImageGenerateRequest, ImageGenerateResponse
from app.services.agnes_image import generate_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image", tags=["image"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image_endpoint(req: ImageGenerateRequest) -> ImageGenerateResponse:
    """Generate an image (txt2img or img2img).

    This is a synchronous endpoint — the Agnes Image API returns results
    directly (unlike the Video API which requires async polling).
    The response may take 10-180 seconds depending on size and mode.
    """
    logger.info("Image generate request: mode=%s, size=%s", req.mode, req.size)
    return await generate_image(req)
