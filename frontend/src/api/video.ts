import api from "./index";

// ─── Types ─────────────────────────────────────────

export type GenerateMode = "txt2vid" | "img2vid";
export type AspectRatio = "16:9" | "9:16" | "1:1" | "4:3";
export type TaskStatus = "idle" | "queued" | "in_progress" | "completed" | "failed" | "timeout";

export interface GenerateRequest {
  mode: GenerateMode;
  prompt: string;
  image?: string | null;
  aspect_ratio: AspectRatio;
  duration: number;
  fps: number;
  negative_prompt?: string;
  num_inference_steps?: number;
  seed?: number | null;
}

export interface TaskResult {
  task_id: string;
  status: TaskStatus;
  video_url: string | null;
  duration: number | null;
  error: string | null;
}

// ─── API functions ────────────────────────────────

/** Submit a video generation task. Returns the task ID.
 * Timeout is 210s because the backend retries on 503 (up to 5 × 15s = 75s) plus
 * the actual API call (up to 120s).
 */
export async function generateVideo(req: GenerateRequest): Promise<string> {
  const resp = await api.post<{ task_id: string; status: string }>("/generate", req, {
    timeout: 210000, // 210 seconds
  });
  return resp.data.task_id;
}

/** Query task status once (returns immediately). */
export async function getTaskStatus(taskId: string): Promise<TaskResult> {
  const resp = await api.get<TaskResult>(`/generate/${taskId}`);
  return resp.data;
}

/** Long-poll: wait until task completes, fails, or times out. */
export async function waitForTask(taskId: string, timeout = 600): Promise<TaskResult> {
  const resp = await api.get<TaskResult>(`/generate/${taskId}/wait`, {
    params: { timeout },
    timeout: (timeout + 30) * 1000, // buffer beyond backend timeout
  });
  return resp.data;
}

/** Build the video stream URL for <video src=...> */
export function getStreamUrl(taskId: string): string {
  return `/api/generate/${taskId}/stream`;
}

/** Build the download URL for <a href=...> */
export function getDownloadUrl(taskId: string): string {
  return `/api/generate/${taskId}/download`;
}
