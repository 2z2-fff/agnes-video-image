"""Pydantic data models for request/response validation."""

from enum import Enum
from pydantic import BaseModel, Field


class GenerateMode(str, Enum):
    """Video generation mode."""
    txt2vid = "txt2vid"
    img2vid = "img2vid"


class GenerateRequest(BaseModel):
    """Request body for POST /api/generate."""
    mode: GenerateMode = GenerateMode.txt2vid
    prompt: str = Field(..., min_length=1, max_length=2000, description="Video content description")
    image: str | None = Field(None, description="Base64-encoded image (img2vid mode only)")
    aspect_ratio: str = Field("16:9", description="Aspect ratio: 16:9, 9:16, 1:1, 4:3")
    duration: float = Field(5.0, ge=2.0, le=17.0, description="Target video duration in seconds (720p max ~17s)")
    fps: int = Field(24, ge=8, le=30, description="Frame rate")
    negative_prompt: str = Field("", description="Negative prompt to exclude unwanted elements")
    num_inference_steps: int = Field(25, ge=1, le=100, description="Number of inference steps")
    seed: int | None = Field(None, description="Random seed for reproducibility")


class TaskResponse(BaseModel):
    """Response for task status queries."""
    task_id: str
    status: str = Field(..., description="queued | in_progress | completed | failed | timeout")
    video_url: str | None = None
    duration: float | None = None
    error: str | None = None


class CreateTaskResponse(BaseModel):
    """Response for POST /api/generate."""
    task_id: str
    status: str = "queued"


# ─── Image generation models ───────────────────────────────────────


class ImageMode(str, Enum):
    """Image generation mode."""
    txt2img = "txt2img"
    img2img = "img2img"


class ImageGenerateRequest(BaseModel):
    """Request body for POST /api/image/generate."""
    mode: ImageMode = ImageMode.txt2img
    prompt: str = Field(..., min_length=1, max_length=2000, description="Image content description")
    image: str | None = Field(None, description="Base64-encoded image (img2img mode only)")
    size: str = Field("1024x1024", description="Output size: 1024x1024, 3840x2160, 2160x3840, 4096x4096")


class ImageGenerateResponse(BaseModel):
    """Response for POST /api/image/generate."""
    image_url: str = Field(..., description="URL path to the generated image (/uploads/xxx.png)")
    revised_prompt: str = Field("", description="Revised prompt from the API, if any")
