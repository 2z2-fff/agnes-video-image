import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  generateVideo,
  getStreamUrl,
  getDownloadUrl,
  getAppConfig,
  waitForTask,
  type AspectRatio,
  type GenerateMode,
  type TaskStatus,
  type VideoSize,
} from "../api/video";

export const useVideoStore = defineStore("video", () => {
  // ─── Form state ───────────────────────────────
  const mode = ref<GenerateMode>("txt2vid");
  const prompt = ref("");
  const negativePrompt = ref("");
  const imagePreview = ref<string | null>(null); // data URL for <img> preview
  const imageBase64 = ref<string | null>(null); // pure base64 for API
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

  // ─── Task state ───────────────────────────────
  const taskStatus = ref<TaskStatus>("idle");
  const taskId = ref<string | null>(null);
  const videoUrl = ref<string | null>(null);
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

  // ─── Actions ─────────────────────────────────
  async function loadConfig() {
    try {
      const cfg = await getAppConfig();
      model.value = cfg.video.model;
      availableSizes.value = cfg.video.sizes;
      availableRatios.value = cfg.video.aspect_ratios;
      minSeconds.value = cfg.video.min_seconds;
      maxSeconds.value = cfg.video.max_seconds;
      // Keep the selection inside what this model accepts.
      if (!cfg.video.sizes.includes(size.value)) {
        size.value = cfg.video.sizes[0];
      }
      if (!cfg.video.aspect_ratios.includes(aspectRatio.value)) {
        aspectRatio.value = cfg.video.aspect_ratios[0];
      }
      if (seconds.value < cfg.video.min_seconds) seconds.value = cfg.video.min_seconds;
      if (seconds.value > cfg.video.max_seconds) seconds.value = cfg.video.max_seconds;
    } catch {
      // Config is a convenience; the backend still validates.
    }
  }

  function setMode(newMode: GenerateMode) {
    mode.value = newMode;
    if (newMode === "txt2vid") {
      imagePreview.value = null;
      imageBase64.value = null;
    }
  }

  function handleImageUpload(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      imagePreview.value = dataUrl;
      // Extract pure base64 (strip data URI prefix); the backend re-encodes to PNG.
      const idx = dataUrl.indexOf(";base64,");
      imageBase64.value = idx !== -1 ? dataUrl.slice(idx + 8) : dataUrl;
    };
    reader.readAsDataURL(file);
  }

  function clearImage() {
    imagePreview.value = null;
    imageBase64.value = null;
  }

  async function generate() {
    if (!prompt.value.trim()) {
      error.value = "请输入视频提示词";
      return;
    }
    if (mode.value === "img2vid" && !imageBase64.value) {
      error.value = "请上传一张图片";
      return;
    }

    taskStatus.value = "queued";
    error.value = null;
    videoUrl.value = null;
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
        aspect_ratio: aspectRatio.value,
        seconds: seconds.value,
        size: size.value,
        negative_prompt: negativePrompt.value || undefined,
        seed: seed.value,
      });

      taskId.value = created.task_id;
      taskStatus.value = "in_progress";

      const result = await waitForTask(created.task_id, 900);

      if (result.status === "completed") {
        taskStatus.value = "completed";
        progress.value = 100;
        videoUrl.value = getStreamUrl(created.task_id);
      } else if (result.status === "failed" || result.status === "timeout") {
        taskStatus.value = result.status;
        error.value = result.error || "生成失败，请重试";
      }
    } catch (e) {
      taskStatus.value = "failed";
      error.value = e instanceof Error ? e.message : "未知错误";
    } finally {
      clearInterval(timer);
    }
  }

  function reset() {
    taskStatus.value = "idle";
    taskId.value = null;
    videoUrl.value = null;
    error.value = null;
    elapsedSec.value = 0;
    progress.value = 0;
  }

  return {
    // form state
    mode,
    prompt,
    negativePrompt,
    imagePreview,
    imageBase64,
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
    // task state
    taskStatus,
    taskId,
    videoUrl,
    error,
    elapsedSec,
    progress,
    // computed
    isGenerating,
    isComplete,
    isFailed,
    streamUrl,
    downloadUrl,
    // actions
    loadConfig,
    setMode,
    handleImageUpload,
    clearImage,
    generate,
    reset,
  };
});
