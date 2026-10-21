import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  generateImage,
  type ImageMode,
  type ImageRatio,
  type ImageSize,
  type ImageTaskStatus,
} from "../api/image";

export const useImageStore = defineStore("image", () => {
  // ─── Form state ───────────────────────────────
  const mode = ref<ImageMode>("txt2img");
  const prompt = ref("");
  const imagePreview = ref<string | null>(null); // data URL for <img> preview
  const imageBase64 = ref<string | null>(null); // full data URI for API
  const size = ref<ImageSize>("1K");
  const ratio = ref<ImageRatio>("1:1");

  // ─── Task state ───────────────────────────────
  const taskStatus = ref<ImageTaskStatus>("idle");
  const resultImageUrl = ref<string | null>(null);
  const revisedPrompt = ref("");
  const error = ref<string | null>(null);
  const elapsedSec = ref(0);

  // ─── Computed ────────────────────────────────
  const isProcessing = computed(() => taskStatus.value === "processing");
  const isComplete = computed(() => taskStatus.value === "complete");
  const isFailed = computed(() => taskStatus.value === "failed");

  // ─── Actions ─────────────────────────────────

  function setMode(newMode: ImageMode) {
    mode.value = newMode;
    // Clear image data only when switching to txt2img (no image needed)
    if (newMode === "txt2img") {
      imagePreview.value = null;
      imageBase64.value = null;
    }
  }

  function handleImageUpload(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      imagePreview.value = dataUrl;
      // Keep the full data URI for the API (includes MIME type)
      imageBase64.value = dataUrl;
    };
    reader.readAsDataURL(file);
  }

  function clearImage() {
    imagePreview.value = null;
    imageBase64.value = null;
  }

  async function generate() {
    if (!prompt.value.trim()) {
      error.value = "请输入图片提示词";
      return;
    }
    if ((mode.value === "img2img" || mode.value === "cartoon") && !imageBase64.value) {
      error.value = "请上传一张参考图片";
      return;
    }

    // Reset state
    taskStatus.value = "processing";
    error.value = null;
    resultImageUrl.value = null;
    revisedPrompt.value = "";
    elapsedSec.value = 0;
    const startTime = Date.now();

    // Elapsed timer
    const timer = setInterval(() => {
      elapsedSec.value = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);

    try {
      const result = await generateImage({
        mode: mode.value,
        prompt: prompt.value,
        image: (mode.value === "img2img" || mode.value === "cartoon") ? imageBase64.value : null,
        size: size.value,
        ratio: ratio.value,
      });

      taskStatus.value = "complete";
      // Add cache-busting query param to prevent stale image
      resultImageUrl.value = `${result.image_url}?t=${Date.now()}`;
      revisedPrompt.value = result.revised_prompt || "";
    } catch (e) {
      taskStatus.value = "failed";
      error.value = e instanceof Error ? e.message : "未知错误";
    } finally {
      clearInterval(timer);
    }
  }

  function reset() {
    taskStatus.value = "idle";
    resultImageUrl.value = null;
    revisedPrompt.value = "";
    error.value = null;
    elapsedSec.value = 0;
  }

  return {
    // form state
    mode,
    prompt,
    imagePreview,
    imageBase64,
    size,
    ratio,
    // task state
    taskStatus,
    resultImageUrl,
    revisedPrompt,
    error,
    elapsedSec,
    // computed
    isProcessing,
    isComplete,
    isFailed,
    // actions
    setMode,
    handleImageUpload,
    clearImage,
    generate,
    reset,
  };
});
