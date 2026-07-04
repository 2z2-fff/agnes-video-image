import api from "./index";

// ─── Types ─────────────────────────────────────────

export type ImageMode = "txt2img" | "img2img";
export type ImageSize = "1024x1024" | "3840x2160" | "2160x3840" | "4096x4096";
export type ImageTaskStatus = "idle" | "processing" | "complete" | "failed";

export interface ImageGenerateRequest {
  mode: ImageMode;
  prompt: string;
  image?: string | null;
  size: ImageSize;
}

export interface ImageGenerateResponse {
  image_url: string;
  revised_prompt: string;
}

// ─── API functions ────────────────────────────────

/** Generate an image (txt2img or img2img).
 * Timeout is 600s (10 min) to cover 4K rate limiting (65s cooldown + retries)
 * plus actual generation time (up to 240s) plus download time.
 */
export async function generateImage(
  req: ImageGenerateRequest
): Promise<ImageGenerateResponse> {
  const resp = await api.post<ImageGenerateResponse>("/image/generate", req, {
    timeout: 600000, // 10 minutes
  });
  return resp.data;
}
