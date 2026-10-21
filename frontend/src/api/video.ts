import api from "./index";

// ─── Types ─────────────────────────────────────────

export type GenerateMode = "txt2vid" | "img2vid" | "reference";
export type AspectRatio = "21:9" | "16:9" | "4:3" | "1:1" | "3:4" | "9:16";
export type VideoSize = "720P" | "1080P" | "1K" | "2K";
export type TaskStatus = "idle" | "queued" | "in_progress" | "completed" | "failed" | "timeout";

export interface GenerateRequest {
  mode: GenerateMode;
  prompt: string;
  /** img2vid: first frame (required) and optional last frame, raw base64 */
  image?: string | null;
  last_image?: string | null;
  /** reference mode: 1..N images, raw base64 */
  images?: string[] | null;
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
  /** Backend-persisted copy (/uploads/videos/xxx.mp4); survives page reloads. */
  local_url: string | null;
  duration: number | null;
  progress: number | null;
  error: string | null;
}

export interface CreateTaskResult {
  task_id?: string;
  job_id?: string;
  status: string;
  model?: string;
  size?: string;
  seconds?: number;
  message?: string;
}

/** One queued job: either still being submitted, or an Agnes task in flight. */
export interface JobResult {
  job_id: string;
  status: string;
  task_id: string | null;
  video_url: string | null;
  local_url: string | null;
  progress: number | null;
  error: string | null;
  prompt?: string | null;
}

/** Backend capability descriptor (GET /api/config). */
export interface AppConfig {
  video: {
    model: string;
    sizes: VideoSize[];
    aspect_ratios: AspectRatio[];
    min_seconds: number;
    max_seconds: number;
    modes: GenerateMode[];
    supports_last_frame: boolean;
    max_reference_images: number;
    /** How long the backend keeps retrying a full queue (drives the client window). */
    queue_wait_minutes: number;
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

/** Submit a video generation task.
 *
 * Returns fast: either `task_id` (accepted immediately) or `job_id`
 * (slow/full queue → backend retries in the background). The server caps its
 * fast attempt at 20s, so 45s here leaves plenty of margin for a large
 * multi-image payload to reach the backend.
 */
export async function generateVideo(req: GenerateRequest): Promise<CreateTaskResult> {
  const resp = await api.post<CreateTaskResult>("/generate", req, {
    timeout: 45000,
  });
  return resp.data;
}

/** Query a queued job (submitting or running). */
export async function getJob(jobId: string): Promise<JobResult> {
  const resp = await api.get<JobResult>(`/jobs/${jobId}`, { timeout: 60000 });
  return resp.data;
}

/**
 * Poll a job until it exposes an Agnes task id (submission accepted) or fails.
 *
 * `timeoutMs` must stay **larger** than the backend's queue budget, otherwise
 * the UI gives up while the backend keeps trying and the task is orphaned.
 * Callers derive it from `/api/config.queue_wait_minutes`.
 */
export async function waitForJobTaskId(
  jobId: string,
  timeoutMs = 2100000,
  onTick?: (job: JobResult) => void,
  isCancelled?: () => boolean
): Promise<JobResult | null> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (isCancelled?.()) {
      return {
        job_id: jobId,
        status: "cancelled",
        task_id: null,
        video_url: null,
        local_url: null,
        progress: null,
        error: "已取消排队",
      };
    }
    const job = await getJob(jobId);
    onTick?.(job);
    if (job.task_id) return job;
    if (job.status === "failed" || job.status === "timeout" || job.status === "cancelled") return job;
    await new Promise((r) => setTimeout(r, 3000));
  }
  return null;
}

/** Cancel a job that is still waiting for queue capacity. */
export async function cancelJob(jobId: string): Promise<void> {
  await api.post(`/jobs/${jobId}/cancel`, null, { timeout: 30000 });
}

/** Query task status once (returns immediately). */
export async function getTaskStatus(taskId: string): Promise<TaskResult> {
  const resp = await api.get<TaskResult>(`/generate/${taskId}`);
  return resp.data;
}

/** Long-poll: wait until task completes, fails, or times out. */
export async function waitForTask(taskId: string, timeout = 1800): Promise<TaskResult> {
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
