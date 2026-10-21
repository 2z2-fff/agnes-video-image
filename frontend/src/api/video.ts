import api from "./index";

// ─── Types ─────────────────────────────────────────

export type GenerateMode = "txt2vid" | "img2vid";
export type AspectRatio = "21:9" | "16:9" | "4:3" | "1:1" | "3:4" | "9:16";
export type VideoSize = "720P" | "1080P" | "1K" | "2K";
export type TaskStatus = "idle" | "queued" | "in_progress" | "completed" | "failed" | "timeout";

export interface GenerateRequest {
  mode: GenerateMode;
  prompt: string;
  image?: string | null;
  aspect_ratio: AspectRatio;
  /** 4–12 seconds (Agnes Video 2.5) */
  seconds: number;
  size: VideoSize;
  negative_prompt?: string;
  seed?: number | null;
}

export interface TaskResult {
  task_id: string;
  status: TaskStatus;
  video_url: string | null;
  duration: number | null;
  progress: number | null;
  error: string | null;
}

export interface CreateTaskResult {
  task_id: string;
  status: string;
  model: string;
  size: string;
  seconds: number;
}

/** Backend capability descriptor (GET /api/config). */
export interface AppConfig {
  video: {
    model: string;
    sizes: VideoSize[];
    aspect_ratios: AspectRatio[];
    min_seconds: number;
    max_seconds: number;
  };
  image: {
    model: string;
    sizes: string[];
    ratios: string[];
    size_labels: Record<string, string>;
    ratio_labels: Record<string, string>;
  };
}

// ─── API functions ────────────────────────────────

/** Submit a video generation task. Returns the task ID.
 * Timeout is 330s: the backend retries a full video queue for up to
 * 20 × 15s = 300s, plus the request itself.
 */
export async function generateVideo(req: GenerateRequest): Promise<CreateTaskResult> {
  const resp = await api.post<CreateTaskResult>("/generate", req, {
    timeout: 330000,
  });
  return resp.data;
}

/** Query task status once (returns immediately). */
export async function getTaskStatus(taskId: string): Promise<TaskResult> {
  const resp = await api.get<TaskResult>(`/generate/${taskId}`);
  return resp.data;
}

/** Long-poll: wait until task completes, fails, or times out. */
export async function waitForTask(taskId: string, timeout = 900): Promise<TaskResult> {
  const resp = await api.get<TaskResult>(`/generate/${taskId}/wait`, {
    params: { timeout },
    timeout: (timeout + 30) * 1000,
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

/** Fetch active models and their accepted values. */
export async function getAppConfig(): Promise<AppConfig> {
  const resp = await api.get<AppConfig>("/config");
  return resp.data;
}
