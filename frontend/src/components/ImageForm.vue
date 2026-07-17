<script setup lang="ts">
import { ref } from "vue";
import { useImageStore } from "../stores/imageStore";
import type { ImageMode, ImageSize } from "../api/image";
import PromptEngineer from "./PromptEngineer.vue";

const store = useImageStore();

const dragOver = ref(false);

const sizeOptions: { label: string; value: ImageSize }[] = [
  { label: "标准 1:1", value: "1024x1024" },
  { label: "4K 16:9", value: "3840x2160" },
  { label: "4K 9:16", value: "2160x3840" },
  { label: "4K 1:1", value: "4096x4096" },
];

const modeTabs: { label: string; value: ImageMode }[] = [
  { label: "文生图", value: "txt2img" },
  { label: "图生图", value: "img2img" },
];

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
  if (store.mode === "img2img" && !store.imageBase64) return false;
  return !store.isProcessing;
}
</script>

<template>
  <div class="image-form">
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

    <!-- Image Upload (img2img only) -->
    <div v-if="store.mode === 'img2img'" class="form-section">
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
        <p class="upload-hint">支持 PNG / JPG / WebP，自动转换为 PNG</p>
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
        图片提示词
        <span class="char-count">{{ store.prompt.length }} / 2000</span>
      </label>
      <div v-if="store.mode === 'img2img'" class="prompt-hint">
        图生图提示：请明确描述要保留的原图要素和要修改的部分。例如「保留原图的构图和人物姿势，将场景改为赛博朋克风格，添加霓虹灯光」
      </div>
      <textarea
        v-model="store.prompt"
        class="prompt-input"
        :placeholder="store.mode === 'img2img'
          ? '例如：保留原图的构图和主体，将场景改为雨夜赛博朋克风格，添加霓虹灯光反射'
          : '描述你想要生成的图片，例如：一只金色的猫坐在窗台上，阳光洒落，温暖的光影，高清细节，电影级构图'"
        rows="4"
        maxlength="2000"
      ></textarea>
    </div>

    <!-- Prompt Engineering -->
    <PromptEngineer mode="image" @apply="store.prompt = $event" />

    <!-- Size Selection -->
    <div class="form-section">
      <label class="form-label">输出尺寸</label>
      <div class="size-group">
        <button
          v-for="opt in sizeOptions"
          :key="opt.value"
          :class="['size-btn', { active: store.size === opt.value }]"
          @click="store.size = opt.value"
        >
          <span class="size-label">{{ opt.label }}</span>
          <span class="size-value">{{ opt.value }}</span>
        </button>
      </div>
      <p v-if="store.size !== '1024x1024'" class="size-hint">
        4K 尺寸有速率限制（每分钟 1 次），如遇限流将自动等待重试
      </p>
    </div>

    <!-- Generate Button -->
    <button
      class="generate-btn"
      :disabled="!canGenerate()"
      @click="store.generate()"
    >
      <span v-if="store.isProcessing" class="spinner"></span>
      {{ store.isProcessing ? "生成中..." : "生成图片" }}
    </button>
  </div>
</template>

<style scoped>
.image-form {
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

/* Prompt hint for img2img */
.prompt-hint {
  padding: 8px 12px;
  background: var(--warning-bg);
  border-left: 3px solid var(--warning);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-default);
  line-height: 1.5;
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

/* Size buttons */
.size-group {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.size-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  transition: all 0.2s;
}

.size-btn.active {
  border-color: var(--primary);
  background: var(--primary-bg);
}

.size-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.size-btn.active .size-label {
  color: var(--primary);
}

.size-value {
  font-size: 10px;
  color: var(--text-dim);
}

.size-hint {
  font-size: 11px;
  color: var(--warning);
  line-height: 1.4;
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
