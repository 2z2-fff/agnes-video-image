import api from "./index";

// ─── Types ─────────────────────────────────────────

export type ImageMode = "txt2img" | "img2img" | "cartoon";
/** Resolution tier accepted by the Agnes image API. */
export type ImageSize = "1K" | "2K" | "3K" | "4K";
export type ImageRatio = "1:1" | "3:4" | "4:3" | "16:9" | "9:16" | "2:3" | "3:2" | "21:9";
export type ImageTaskStatus = "idle" | "processing" | "complete" | "failed";

export interface ImageGenerateRequest {
  mode: ImageMode;
  prompt: string;
  image?: string | null;
  size: ImageSize;
  ratio: ImageRatio;
}

export interface ImageGenerateResponse {
  image_url: string;
  revised_prompt: string;
  size: string;
  ratio: string;
}

/** Output dimensions per tier, from the official docs table. */
export const IMAGE_DIMENSIONS: Record<ImageRatio, Record<ImageSize, string>> = {
  "1:1": { "1K": "1024×1024", "2K": "2048×2048", "3K": "3072×3072", "4K": "4096×4096" },
  "3:4": { "1K": "864×1152", "2K": "1728×2304", "3K": "2592×3456", "4K": "3456×4608" },
  "4:3": { "1K": "1152×864", "2K": "2304×1728", "3K": "3456×2592", "4K": "4608×3456" },
  "16:9": { "1K": "1312×736", "2K": "2624×1472", "3K": "3936×2208", "4K": "5248×2944" },
  "9:16": { "1K": "736×1312", "2K": "1472×2624", "3K": "2208×3936", "4K": "2944×5248" },
  "2:3": { "1K": "832×1248", "2K": "1664×2496", "3K": "2496×3744", "4K": "3328×4992" },
  "3:2": { "1K": "1248×832", "2K": "2496×1664", "3K": "3744×2496", "4K": "4992×3328" },
  "21:9": { "1K": "1568×672", "2K": "3136×1344", "3K": "4704×2016", "4K": "6272×2688" },
};

// ─── API functions ────────────────────────────────

/** Generate an image (txt2img / img2img / cartoon).
 * Timeout is 600s to cover retries (429/503 backoff) plus generation and download.
 */
export async function generateImage(
  req: ImageGenerateRequest
): Promise<ImageGenerateResponse> {
  const resp = await api.post<ImageGenerateResponse>("/image/generate", req, {
    timeout: 600000,
  });
  return resp.data;
}
