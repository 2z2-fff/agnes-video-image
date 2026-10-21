<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useVideoStore } from "../stores/videoStore";
import type { GenerateMode, VideoSize } from "../api/video";
import PromptEngineer from "./PromptEngineer.vue";

const store = useVideoStore();

const showAdvanced = ref(false);
const dragOver = ref(false);

const durationPresets = [4, 5, 6, 8, 10, 12];

const sizeLabels: Record<VideoSize, string> = {
  "720P": "720P 标准",
  "1080P": "1080P 高清",
  "1K": "1K",
  "2K": "2K 超清",
};

const modeTabs: { label: string; value: GenerateMode }[] = [
  { label: "文生视频", value: "txt2vid" },
  { label: "图生视频", value: "img2vid" },
];

// Only offer what the active model accepts (Flash = 720P only).
const sizeOptions = computed(() =>
  store.availableSizes.map((s) => ({ value: s, label: sizeLabels[s] ?? s }))
);

const flashOnlyHint = computed(
  () => store.availableSizes.length === 1 && store.model.includes("flash")
);

onMounted(() => {
  store.loadConfig();
});

function onDrop(e: DragEvent) {
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file && file.type.startsWith("image/")) {
    store.handleImageUpload(file);
  }
}

function onFileSelect(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (file) {
    store.handleImageUpload(file);
  }
}

function canGenerate(): boolean {
  if (!store.prompt.trim()) return false;
  if (store.mode === "img2vid" && !store.imageBase64) return false;
  return !store.isGenerating;
}
</script>

<template>
  <div class="video-form">
    <!-- Mode Selector -->
    <div class="mode-tabs">
      <button
        v-for="tab in modeTabs"
        :key="tab.value"
        :class="['mode-tab', { active: store.mode === tab.value }]"
        @click="store.setMode(tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Image Upload (img2vid only) -->
    <div v-if="store.mode === 'img2vid'" class="form-section">
      <label class="form-label">参考图片</label>
      <div
        v-if="!store.imagePreview"
        class="upload-zone"
        :class="{ dragover: dragOver }"
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        <svg class="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 16V4M12 4L7 9M12 4L17 9" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M3 15v4a2 2 0 002 2h14a2 2 0 002-2v-4" stroke-linecap="round" />
        </svg>
        <p class="upload-text">拖拽图片到此处或<span class="upload-link">点击上传</span></p>
        <p class="upload-hint">支持 PNG / JPG / WebP</p>
        <input type="file" accept="image/*" class="file-input" @change="onFileSelect" />
      </div>
      <div v-else class="image-preview">
        <img :src="store.imagePreview" alt="参考图片" class="preview-img" />
        <button class="remove-btn" @click="store.clearImage">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Prompt Input -->
    <div class="form-section">
      <label class="form-label">
        视频提示词
        <span class="char-count">{{ store.prompt.length }} / 2000</span>
      </label>
      <textarea
        v-model="store.prompt"
        class="prompt-input"
        placeholder="描述你想要生成的视频内容，例如：一只金色的猫在日落时分的海滩上漫步，海浪轻轻拍打沙滩，暖金色的光线，电影级画面"
        rows="4"
        maxlength="2000"
      ></textarea>
    </div>

    <!-- Prompt Engineering -->
    <PromptEngineer mode="video" @apply="store.prompt = $event" />

    <!-- Aspect Ratio -->
    <div class="form-section">
      <label class="form-label">宽高比</label>
      <div class="ratio-group">
        <button
          v-for="r in store.availableRatios"
          :key="r"
          :class="['ratio-btn', { active: store.aspectRatio === r }]"
          @click="store.aspectRatio = r"
        >
          {{ r }}
        </button>
      </div>
    </div>

    <!-- Duration -->
    <div class="form-section">
      <label class="form-label">
        视频时长
        <span class="char-count">4–12 秒</span>
      </label>
      <div class="duration-group">
        <button
          v-for="d in durationPresets"
          :key="d"
          :disabled="d < store.minSeconds || d > store.maxSeconds"
          :class="['duration-btn', { active: store.seconds === d }]"
          @click="store.seconds = d"
        >
          {{ d }}秒
        </button>
      </div>
    </div>

    <!-- Resolution tier -->
    <div class="form-section">
      <label class="form-label">
        分辨率
        <span v-if="store.model" class="char-count">{{ store.model }}</span>
      </label>
      <div class="ratio-group">
        <button
          v-for="opt in sizeOptions"
          :key="opt.value"
          :class="['ratio-btn', { active: store.size === opt.value }]"
          @click="store.size = opt.value"
        >
          {{ opt.label }}
        </button>
      </div>
      <p v-if="flashOnlyHint" class="upload-hint">
        当前为 Flash 模型，仅支持 720P 且限时免费；如需 1080P/2K，请将后端
        <code>AGNES_VIDEO_MODEL</code> 改为 <code>agnes-video-2.5</code>（按秒计费）。
      </p>
    </div>

    <!-- Advanced Settings -->
    <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
      <svg
        class="chevron"
        :class="{ rotated: showAdvanced }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      高级设置
    </button>

    <div v-show="showAdvanced" class="advanced-panel">
      <div class="form-row">
        <label class="form-label">随机种子（留空为随机）</label>
        <input
          type="number"
          v-model.number="store.seed"
          placeholder="例如: 42"
          class="text-input"
        />
      </div>

      <div class="form-row">
        <label class="form-label">负面提示词（附加到提示词末尾）</label>
        <textarea
          v-model="store.negativePrompt"
          class="prompt-input"
          placeholder="排除不想要的元素，例如：no camera shake, no morphing, stable appearance"
          rows="2"
        ></textarea>
      </div>
    </div>

    <!-- Generate Button -->
    <button
      class="generate-btn"
      :disabled="!canGenerate()"
      @click="store.generate()"
    >
      <span v-if="store.isGenerating" class="spinner"></span>
      {{ store.isGenerating ? "生成中..." : "生成视频" }}
    </button>
  </div>
</template>

<style scoped>
.video-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Mode tabs */
.mode-tabs {
  display: flex;
  background: var(--surface-input);
  border-radius: var(--radius);
  padding: 3px;
}

.mode-tab {
  flex: 1;
  padding: 8px 16px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.mode-tab.active {
  background: var(--bg);
  color: var(--primary);
  box-shadow: var(--shadow-sm);
}

/* Form sections */
.form-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.char-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-dim);
}

/* Upload zone */
.upload-zone {
  position: relative;
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 32px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-zone.dragover {
  border-color: var(--primary);
  background: var(--primary-bg);
}

.upload-icon {
  width: 32px;
  height: 32px;
  color: var(--text-dim);
  margin-bottom: 8px;
}

.upload-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.upload-link {
  color: var(--primary);
  font-weight: 500;
}

.upload-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 4px;
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

/* Image preview */
.image-preview {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--surface-card);
}

.preview-img {
  width: 100%;
  max-height: 200px;
  object-fit: contain;
}

.remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn svg {
  width: 16px;
  height: 16px;
}

/* Prompt input */
.prompt-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-input);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  transition: border-color 0.2s;
}

.prompt-input:focus {
  outline: none;
  border-color: var(--primary);
}

.prompt-input::placeholder {
  color: var(--text-muted);
}

/* Ratio buttons */
.ratio-group,
.duration-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ratio-btn,
.duration-btn {
  flex: 1;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.ratio-btn.active,
.duration-btn.active {
  border-color: var(--primary);
  background: var(--primary-bg);
  color: var(--primary);
}

/* Advanced settings */
.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 0;
}

.chevron {
  width: 16px;
  height: 16px;
  transition: transform 0.2s;
}

.chevron.rotated {
  transform: rotate(90deg);
}

.advanced-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--surface-card);
  border-radius: var(--radius);
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.slider {
  width: 100%;
  height: 4px;
  background: var(--surface-elevated);
  border-radius: 2px;
  appearance: none;
  outline: none;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--primary);
  cursor: pointer;
}

.text-input {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text-primary);
  font-size: 13px;
}

.text-input:focus {
  outline: none;
  border-color: var(--primary);
}

/* Generate button */
.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 12px;
  border-radius: var(--radius);
  background: var(--primary);
  color: var(--text-on-primary);
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
}

.generate-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
