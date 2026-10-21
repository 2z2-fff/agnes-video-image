"""Pydantic data models for request/response validation."""

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import (
    IMAGE_RATIOS,
    IMAGE_SIZES,
    VIDEO_ASPECT_RATIOS,
    VIDEO_MAX_SECONDS,
    VIDEO_MIN_SECONDS,
    VIDEO_SIZES,
)


class GenerateMode(str, Enum):
    """Video generation mode.

    These are UI-level names; the service maps them onto the API's `mode`:

    * ``txt2vid``   -> ``text``     (prompt only)
    * ``img2vid``   -> ``keyframe`` (first_frame, optional last_frame)
    * ``reference`` -> ``reference``(images[] used as content/style references)
    """

    txt2vid = "txt2vid"
    img2vid = "img2vid"
    reference = "reference"


class GenerateRequest(BaseModel):
    """Request body for POST /api/generate."""

    mode: GenerateMode = GenerateMode.txt2vid
    prompt: str = Field(..., min_length=1, max_length=2000, description="Video content description")
    image: str | None = Field(
        None,
        description="img2vid first frame: data URI or raw base64 (converted to PNG)",
    )
    last_image: str | None = Field(
        None,
        description="img2vid optional last frame: data URI or raw base64. "
        "Supplying it turns the task into a first/last-frame transition.",
    )
    images: list[str] | None = Field(
        None,
        description="reference mode: 1..N images (N = 8 for agnes-video-2.5, 5 for Flash). "
        "Refer to them in the prompt as <Picture 1>, <Picture 2>, ...",
    )
    aspect_ratio: str = Field("16:9", description="21:9, 16:9, 4:3, 1:1, 3:4, 9:16")
    seconds: int = Field(
        5,
        ge=VIDEO_MIN_SECONDS,
        le=VIDEO_MAX_SECONDS,
        description="Video duration in seconds (4-12)",
    )
    size: str = Field("720P", description="Output tier: 720P, 1080P, 1K, 2K")
    seed: int | None = Field(None, description="Random seed for reproducibility")
    negative_prompt: str = Field(
        "",
        description="Legacy field. Video 2.5 has no negative_prompt parameter; "
        "its content is appended to the prompt instead.",
    )

    @field_validator("aspect_ratio")
    @classmethod
    def _validate_aspect(cls, v: str) -> str:
        if v not in VIDEO_ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio must be one of {list(VIDEO_ASPECT_RATIOS)}")
        return v

    @field_validator("size")
    @classmethod
    def _validate_size(cls, v: str) -> str:
        if v not in VIDEO_SIZES:
            raise ValueError(f"size must be one of {list(VIDEO_SIZES)}")
        return v

    @model_validator(mode="after")
    def _validate_media_for_mode(self) -> "GenerateRequest":
        """Enforce the API's mutually exclusive media rules.

        The service rejects a body that mixes `first_frame`/`last_frame` with
        `images`, so catch it here with a clear message instead of a raw 400.
        """
        images = [i for i in (self.images or []) if i]

        if self.mode == GenerateMode.txt2vid:
            if self.image or self.last_image or images:
                raise ValueError("文生视频模式不接受参考图片，请切换到图生视频或多图参考")
        elif self.mode == GenerateMode.img2vid:
            if not self.image:
                raise ValueError("图生视频模式需要上传首帧图片")
            if images:
                raise ValueError("首帧/尾帧 与 多图参考 不能同时使用，请分别提交")
        else:  # reference
            if not images:
                raise ValueError("多图参考模式至少需要上传 1 张图片")
            if self.image or self.last_image:
                raise ValueError("多图参考模式不能同时使用首帧/尾帧")
            if len(images) > 8:
                raise ValueError("参考图片最多 8 张")

        return self


class TaskResponse(BaseModel):
    """Response for task status queries."""

    task_id: str
    status: str = Field(..., description="queued | in_progress | completed | failed | timeout")
    video_url: str | None = None
    duration: float | None = None
    progress: int | None = None
    error: str | None = None


class CreateTaskResponse(BaseModel):
    """Response for POST /api/generate."""

    task_id: str
    status: str = "queued"
    model: str = ""
    size: str = ""
    seconds: int = 0


# ─── Image generation models ───────────────────────────────────────


class ImageMode(str, Enum):
    """Image generation mode."""

    txt2img = "txt2img"
    img2img = "img2img"
    cartoon = "cartoon"


class ImageGenerateRequest(BaseModel):
    """Request body for POST /api/image/generate."""

    mode: ImageMode = ImageMode.txt2img
    prompt: str = Field(..., min_length=1, max_length=2000, description="Image content description")
    image: str | None = Field(
        None,
        description="Reference image for img2img/cartoon: data URI or raw base64",
    )
    size: str = Field("1K", description="Output tier: 1K, 2K, 3K, 4K")
    ratio: str = Field("1:1", description="Aspect ratio: 1:1, 16:9, 9:16, 4:3, 3:4, 2:3, 3:2, 21:9")

    @field_validator("size")
    @classmethod
    def _validate_size(cls, v: str) -> str:
        if v not in IMAGE_SIZES:
            raise ValueError(f"size must be one of {list(IMAGE_SIZES)}")
        return v

    @field_validator("ratio")
    @classmethod
    def _validate_ratio(cls, v: str) -> str:
        if v not in IMAGE_RATIOS:
            raise ValueError(f"ratio must be one of {list(IMAGE_RATIOS)}")
        return v


class ImageGenerateResponse(BaseModel):
    """Response for POST /api/image/generate."""

    image_url: str = Field(..., description="URL path to the generated image (/uploads/xxx.png)")
    revised_prompt: str = Field("", description="Revised prompt from the API, if any")
    size: str = Field("", description="Requested size tier")
    ratio: str = Field("", description="Requested aspect ratio")
