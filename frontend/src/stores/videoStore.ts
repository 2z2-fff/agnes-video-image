import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  generateVideo,
  getStreamUrl,
  getDownloadUrl,
  getAppConfig,
  waitForTask,
  waitForJobTaskId,
  type AspectRatio,
  type GenerateMode,
  type TaskStatus,
  type VideoSize,
} from "../api/video";
import { loadJSON, saveJSON, removeKey } from "../lib/persist";

const STORAGE_KEY = "video.last";

/** Shape persisted in localStorage so a reload keeps the last result. */
interface PersistedVideo {
  taskId: string | null;
  jobId: string | null;
  status: TaskStatus;
  videoUrl: string | null;
  localUrl: string | null;
  prompt: string;
  mode: GenerateMode;
  aspectRatio: AspectRatio;
  seconds: number;
  size: VideoSize;
  error: string | null;
  elapsedSec: number;
  ts: number;
}

/** One uploaded reference image (reference mode). */
export interface ReferenceImage {
  preview: string; // data URL for <img>
  base64: string;  // raw base64 for the API
}

function toBase64(dataUrl: string): string {
  const idx = dataUrl.indexOf(";base64,");
  return idx !== -1 ? dataUrl.slice(idx + 8) : dataUrl;
}

export const useVideoStore = defineStore("video", () => {
  // ─── Form state ───────────────────────────────
  const mode = ref<GenerateMode>("txt2vid");
  const prompt = ref("");
  const negativePrompt = ref("");
  const imagePreview = ref<string | null>(null); // first frame preview
  const imageBase64 = ref<string | null>(null); // first frame, raw base64
  const lastImagePreview = ref<string | null>(null); // optional last frame
  const lastImageBase64 = ref<string | null>(null);
  const referenceImages = ref<ReferenceImage[]>([]); // reference mode
  const aspectRatio = ref<AspectRatio>("16:9");
  const seconds = ref(5);
  const size = ref<VideoSize>("720P");
  const seed = ref<number | null>(null);

  // ─── Capabilities (from GET /api/config) ──────
  const model = ref("");
  const availableSizes = ref<VideoSize[]>(["720P"]);
  const availableRatios = ref<AspectRatio[]>([
    "21:9",
    "16:9",
    "4:3",
    "1:1",
    "3:4",
    "9:16",
  ]);
  const minSeconds = ref(4);
  const maxSeconds = ref(12);
  const supportsLastFrame = ref(true);
  const maxReferenceImages = ref(8);

  // ─── Task state ───────────────────────────────
  const taskStatus = ref<TaskStatus>("idle");
  const taskId = ref<string | null>(null);
  const jobId = ref<string | null>(null); // local job id while the queue is full
  const videoUrl = ref<string | null>(null);
  const localUrl = ref<string | null>(null); // /uploads/videos/... copy served by the backend
  const error = ref<string | null>(null);
  const elapsedSec = ref(0);
  const progress = ref(0);

  // ─── Computed ────────────────────────────────
  const isGenerating = computed(
    () => taskStatus.value === "queued" || taskStatus.value === "in_progress"
  );
  const isComplete = computed(() => taskStatus.value === "completed");
  const isFailed = computed(
    () => taskStatus.value === "failed" || taskStatus.value === "timeout"
  );
  const streamUrl = computed(() =>
    taskId.value ? getStreamUrl(taskId.value) : null
  );
  const downloadUrl = computed(() =>
    taskId.value ? getDownloadUrl(taskId.value) : null
  );
  const isKeyframeMode = computed(() => mode.value === "img2vid");
  const isReferenceMode = computed(() => mode.value === "reference");

  // ─── Actions ─────────────────────────────────
  async function loadConfig() {
    try {
      const cfg = await getAppConfig();
      model.value = cfg.video.model;
      availableSizes.value = cfg.video.sizes;
      availableRatios.value = cfg.video.aspect_ratios;
      minSeconds.value = cfg.video.min_seconds;
      maxSeconds.value = cfg.video.max_seconds;
      supportsLastFrame.value = cfg.video.supports_last_frame ?? true;
      maxReferenceImages.value = cfg.video.max_reference_images ?? 8;

      if (!cfg.video.sizes.includes(size.value)) {
        size.value = cfg.video.sizes[0];
      }
      if (!cfg.video.aspect_ratios.includes(aspectRatio.value)) {
        aspectRatio.value = cfg.video.aspect_ratios[0];
      }
      if (seconds.value < cfg.video.min_seconds) seconds.value = cfg.video.min_seconds;
      if (seconds.value > cfg.video.max_seconds) seconds.value = cfg.video.max_seconds;
    } catch {
      // Config is a convenience; the backend still validates everything.
    }
  }

  function clearKeyframe() {
    imagePreview.value = null;
    imageBase64.value = null;
    lastImagePreview.value = null;
    lastImageBase64.value = null;
  }

  function clearReferences() {
    referenceImages.value = [];
  }

  function setMode(newMode: GenerateMode) {
    mode.value = newMode;
    // Media from one mode is invalid in another (the API treats them as exclusive).
    if (newMode === "txt2vid") {
      clearKeyframe();
      clearReferences();
    } else if (newMode === "img2vid") {
      clearReferences();
    } else {
      clearKeyframe();
    }
  }

  function _readFile(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function handleImageUpload(file: File) {
    const dataUrl = await _readFile(file);
    imagePreview.value = dataUrl;
    imageBase64.value = toBase64(dataUrl);
  }

  async function handleLastImageUpload(file: File) {
    const dataUrl = await _readFile(file);
    lastImagePreview.value = dataUrl;
    lastImageBase64.value = toBase64(dataUrl);
  }

  function clearImage() {
    imagePreview.value = null;
    imageBase64.value = null;
  }

  function clearLastImage() {
    lastImagePreview.value = null;
    lastImageBase64.value = null;
  }

  async function addReferenceImages(files: File[] | FileList) {
    for (const file of Array.from(files)) {
      if (referenceImages.value.length >= maxReferenceImages.value) {
        error.value = `参考图片最多 ${maxReferenceImages.value} 张`;
        break;
      }
      if (!file.type.startsWith("image/")) continue;
      const dataUrl = await _readFile(file);
      referenceImages.value.push({ preview: dataUrl, base64: toBase64(dataUrl) });
    }
  }

  function removeReferenceImage(index: number) {
    referenceImages.value.splice(index, 1);
  }

  async function generate() {
    if (!prompt.value.trim()) {
      error.value = "请输入视频提示词";
      return;
    }
    if (mode.value === "img2vid" && !imageBase64.value) {
      error.value = "请上传首帧图片";
      return;
    }
    if (mode.value === "reference") {
      if (referenceImages.value.length === 0) {
        error.value = "请至少上传 1 张参考图片";
        return;
      }
      if (referenceImages.value.length > maxReferenceImages.value) {
        error.value = `参考图片最多 ${maxReferenceImages.value} 张`;
        return;
      }
    }

    taskStatus.value = "queued";
    error.value = null;
    videoUrl.value = null;
    localUrl.value = null;
    progress.value = 0;
    elapsedSec.value = 0;
    const startTime = Date.now();

    const timer = setInterval(() => {
      elapsedSec.value = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);

    try {
      const created = await generateVideo({
        mode: mode.value,
        prompt: prompt.value,
        image: mode.value === "img2vid" ? imageBase64.value : null,
        last_image: mode.value === "img2vid" ? lastImageBase64.value : null,
        images:
          mode.value === "reference"
            ? referenceImages.value.map((r) => r.base64)
            : null,
        aspect_ratio: aspectRatio.value,
        seconds: seconds.value,
        size: size.value,
        negative_prompt: negativePrompt.value || undefined,
        seed: seed.value,
      });

      // Two shapes: accepted immediately (task_id) or queued because the shared
      // queue is full (job_id → backend retries in the background).
      let agnesTaskId = created.task_id ?? null;

      if (!agnesTaskId && created.job_id) {
        jobId.value = created.job_id;
        taskStatus.value = "queued";
        persist();

        const job = await waitForJobTaskId(created.job_id, 900000, (tick) => {
          if (tick.progress != null) progress.value = tick.progress;
          taskStatus.value = tick.task_id ? "in_progress" : "queued";
        });

        if (!job?.task_id) {
          taskStatus.value = job?.status === "timeout" ? "timeout" : "failed";
          error.value = job?.error || "排队超时，任务未能提交（未创建任务、未计费）";
          return;
        }
        agnesTaskId = job.task_id;
        progress.value = job.progress ?? 0;
      }

      if (!agnesTaskId) {
        taskStatus.value = "failed";
        error.value = "服务端未返回任务 ID";
        return;
      }

      taskId.value = agnesTaskId;
      taskStatus.value = "in_progress";
      // Persist the id immediately: a reload must not orphan a queued task.
      persist();

      await awaitTaskFinish(agnesTaskId);
    } catch (e) {
      taskStatus.value = "failed";
      error.value = e instanceof Error ? e.message : "未知错误";
    } finally {
      clearInterval(timer);
      persist();
    }
  }

  /** Wait for an Agnes task to finish and apply the result to the store. */
  async function awaitTaskFinish(id: string) {
    const result = await waitForTask(id, 1800);
    if (result.status === "completed") {
      taskStatus.value = "completed";
      progress.value = 100;
      localUrl.value = result.local_url ?? null;
      // Prefer the backend's local copy: it outlives Agnes' temporary URL.
      videoUrl.value = result.local_url || getStreamUrl(id);
    } else if (result.status === "failed" || result.status === "timeout") {
      taskStatus.value = result.status;
      error.value = result.error || "生成失败，请重试";
    }
  }

  // ─── Persistence / resume ─────────────────────

  /** Write the current task state to localStorage. */
  function persist() {
    if (!taskId.value && !jobId.value && taskStatus.value === "idle") {
      removeKey(STORAGE_KEY);
      return;
    }
    saveJSON(STORAGE_KEY, {
      taskId: taskId.value,
      jobId: jobId.value,
      status: taskStatus.value,
      videoUrl: videoUrl.value,
      localUrl: localUrl.value,
      prompt: prompt.value,
      mode: mode.value,
      aspectRatio: aspectRatio.value,
      seconds: seconds.value,
      size: size.value,
      error: error.value,
      elapsedSec: elapsedSec.value,
      ts: Date.now(),
    } satisfies PersistedVideo);
  }

  /** Restore the last result (or resume polling an unfinished task) on startup. */
  async function restore() {
    const saved = loadJSON<PersistedVideo>(STORAGE_KEY);
    if (!saved) return;
    if (!saved.taskId && !saved.jobId) return;

    taskId.value = saved.taskId ?? null;
    jobId.value = saved.jobId ?? null;
    prompt.value = saved.prompt ?? prompt.value;
    mode.value = saved.mode ?? mode.value;
    aspectRatio.value = saved.aspectRatio ?? aspectRatio.value;
    seconds.value = saved.seconds ?? seconds.value;
    size.value = saved.size ?? size.value;

    if (saved.status === "completed" && (saved.localUrl || saved.videoUrl)) {
      taskStatus.value = "completed";
      progress.value = 100;
      localUrl.value = saved.localUrl ?? null;
      videoUrl.value = saved.localUrl || saved.videoUrl;
      return;
    }

    if (saved.status === "failed" || saved.status === "timeout") {
      taskStatus.value = saved.status;
      error.value = saved.error ?? null;
      return;
    }

    taskStatus.value = saved.status === "queued" ? "queued" : "in_progress";

    // Submission was still queued → resume the job, then continue with the task.
    if (!saved.taskId && saved.jobId) {
      resumeJob(saved.jobId);
      return;
    }
    if (saved.taskId) resumePolling(saved.taskId);
  }

  /** Re-attach to a job that was still waiting for queue capacity. */
  async function resumeJob(id: string) {
    try {
      const job = await waitForJobTaskId(id, 900000, (tick) => {
        if (tick.progress != null) progress.value = tick.progress;
        taskStatus.value = tick.task_id ? "in_progress" : "queued";
      });
      if (!job?.task_id) {
        taskStatus.value = job?.status === "timeout" ? "timeout" : "failed";
        error.value = job?.error || "排队超时，任务未能提交";
        return;
      }
      taskId.value = job.task_id;
      taskStatus.value = "in_progress";
      persist();
      await resumePolling(job.task_id);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "恢复排队任务失败";
      persist();
    }
  }

  /** Re-attach to a task that was running when the page was closed. */
  async function resumePolling(id: string) {
    const startTime = Date.now() - elapsedSec.value * 1000;
    const timer = setInterval(() => {
      elapsedSec.value = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);
    try {
      const result = await waitForTask(id, 1800);
      if (result.status === "completed") {
        taskStatus.value = "completed";
        progress.value = 100;
        localUrl.value = result.local_url ?? null;
        videoUrl.value = result.local_url || getStreamUrl(id);
      } else if (result.status === "failed" || result.status === "timeout") {
        taskStatus.value = result.status;
        error.value = result.error || "生成失败，请重试";
      }
    } catch (e) {
      // Keep the restored state; the user can retry the query.
      error.value = e instanceof Error ? e.message : "恢复任务状态失败";
    } finally {
      clearInterval(timer);
      persist();
    }
  }

  /** Load a past generation from the history list into the result panel. */
  function loadFromHistory(record: {
    taskId: string;
    videoUrl: string | null;
    prompt?: string;
  }) {
    taskId.value = record.taskId;
    taskStatus.value = "completed";
    progress.value = 100;
    localUrl.value = record.videoUrl?.startsWith("/uploads/") ? record.videoUrl : null;
    videoUrl.value = record.videoUrl;
    prompt.value = record.prompt ?? prompt.value;
    error.value = null;
    persist();
  }

  function reset() {
    taskStatus.value = "idle";
    taskId.value = null;
    jobId.value = null;
    videoUrl.value = null;
    localUrl.value = null;
    error.value = null;
    elapsedSec.value = 0;
    progress.value = 0;
    removeKey(STORAGE_KEY);
  }

  return {
    // form state
    mode,
    prompt,
    negativePrompt,
    imagePreview,
    imageBase64,
    lastImagePreview,
    lastImageBase64,
    referenceImages,
    aspectRatio,
    seconds,
    size,
    seed,
    // capabilities
    model,
    availableSizes,
    availableRatios,
    minSeconds,
    maxSeconds,
    supportsLastFrame,
    maxReferenceImages,
    // task state
    taskStatus,
    taskId,
    jobId,
    videoUrl,
    localUrl,
    error,
    elapsedSec,
    progress,
    // computed
    isGenerating,
    isComplete,
    isFailed,
    streamUrl,
    downloadUrl,
    isKeyframeMode,
    isReferenceMode,
    // actions
    loadConfig,
    setMode,
    handleImageUpload,
    handleLastImageUpload,
    clearImage,
    clearLastImage,
    addReferenceImages,
    removeReferenceImage,
    clearReferences,
    generate,
    restore,
    loadFromHistory,
    reset,
  };
});
