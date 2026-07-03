import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  generateVideo,
  waitForTask,
  getStreamUrl,
  getDownloadUrl,
  type GenerateMode,
  type AspectRatio,
  type TaskStatus,
} from "../api/video";

export const useVideoStore = defineStore("video", () => {
  // ─── Form state ───────────────────────────────
  const mode = ref<GenerateMode>("txt2vid");
  const prompt = ref("");
  const negativePrompt = ref("");
  const imagePreview = ref<string | null>(null); // data URL for <img> preview
  const imageBase64 = ref<string | null>(null); // pure base64 for API
  const aspectRatio = ref<AspectRatio>("16:9");
  const duration = ref(5);
  const fps = ref(24);
  const inferenceSteps = ref(25);
  const seed = ref<number | null>(null);

  // ─── Task state ───────────────────────────────
  const taskStatus = ref<TaskStatus>("idle");
  const taskId = ref<string | null>(null);
  const videoUrl = ref<string | null>(null);
  const error = ref<string | null>(null);
  const elapsedSec = ref(0);

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
      // Extract pure base64 (strip data URI prefix)
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

    // Reset state
    taskStatus.value = "queued";
    error.value = null;
    videoUrl.value = null;
    elapsedSec.value = 0;
    const startTime = Date.now();

    // Elapsed timer
    const timer = setInterval(() => {
      elapsedSec.value = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);

    try {
      // Step 1: Submit task
      const id = await generateVideo({
        mode: mode.value,
        prompt: prompt.value,
        image: mode.value === "img2vid" ? imageBase64.value : null,
        aspect_ratio: aspectRatio.value,
        duration: duration.value,
        fps: fps.value,
        negative_prompt: negativePrompt.value || undefined,
        num_inference_steps: inferenceSteps.value,
        seed: seed.value,
      });

      taskId.value = id;
      taskStatus.value = "in_progress";

      // Step 2: Wait for completion (long-poll)
      const result = await waitForTask(id, 600);

      if (result.status === "completed") {
        taskStatus.value = "completed";
        // Use proxied stream URL instead of the raw Agnes URL
        videoUrl.value = getStreamUrl(id);
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
  }

  return {
    // form state
    mode,
    prompt,
    negativePrompt,
    imagePreview,
    imageBase64,
    aspectRatio,
    duration,
    fps,
    inferenceSteps,
    seed,
    // task state
    taskStatus,
    taskId,
    videoUrl,
    error,
    elapsedSec,
    // computed
    isGenerating,
    isComplete,
    isFailed,
    streamUrl,
    downloadUrl,
    // actions
    setMode,
    handleImageUpload,
    clearImage,
    generate,
    reset,
  };
});
