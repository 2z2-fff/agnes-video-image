<script setup lang="ts">
import { useImageStore } from "../stores/imageStore";

const store = useImageStore();

function formatTime(sec: number): string {
  if (sec < 60) return `${sec}秒`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}分${s}秒`;
}

// Aspect-ratio keyed by the requested ratio (tier no longer implies a shape).
const ratioAspect: Record<string, string> = {
  "1:1": "1 / 1",
  "16:9": "16 / 9",
  "9:16": "9 / 16",
  "4:3": "4 / 3",
  "3:4": "3 / 4",
  "3:2": "3 / 2",
  "2:3": "2 / 3",
  "21:9": "21 / 9",
};
</script>

<template>
  <!-- Idle state -->
  <div v-if="store.taskStatus === 'idle'" class="status-container idle">
    <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="M21 15l-5-5L5 21" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    <p class="status-text">填写参数后点击生成图片</p>
  </div>

  <!-- Processing state -->
  <div v-else-if="store.isProcessing" class="status-container loading">
    <div class="loading-spinner"></div>
    <p class="status-text">图片生成中...</p>
    <p class="status-hint">4K 图片可能需要 2-5 分钟</p>
    <p v-if="store.elapsedSec > 0" class="status-timer">已等待 {{ formatTime(store.elapsedSec) }}</p>
  </div>

  <!-- Complete state -->
  <div v-else-if="store.isComplete && store.resultImageUrl" class="result-area">
    <div
      class="image-wrapper"
      :style="{ aspectRatio: ratioAspect[store.ratio] || '1 / 1' }"
    >
      <img
        :src="store.resultImageUrl"
        alt="生成的图片"
        class="result-image"
      />
    </div>

    <div v-if="store.revisedPrompt" class="revised-prompt">
      <span class="revised-label">API 优化后的提示词:</span>
      <p class="revised-text">{{ store.revisedPrompt }}</p>
    </div>

    <div class="image-actions">
      <a
        :href="store.resultImageUrl"
        download="agnes-generated.png"
        class="action-btn download-btn"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <path d="M12 4v12M12 16l-4-4M12 16l4-4" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M4 20h16" stroke-linecap="round" />
        </svg>
        下载图片
      </a>
      <button class="action-btn regenerate-btn" @click="store.generate()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <path d="M4 4v6h6M20 20v-6h-6" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M4 10a8 8 0 0114-4l2 2M20 14a8 8 0 01-14 4l-2-2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        重新生成
      </button>
    </div>
  </div>

  <!-- Failed state -->
  <div v-else-if="store.isFailed" class="status-container failed">
    <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" stroke-linecap="round" />
    </svg>
    <p class="status-text">生成失败</p>
    <p v-if="store.error" class="status-error">{{ store.error }}</p>
    <button class="retry-btn" @click="store.generate()">
      重试
    </button>
  </div>
</template>

<style scoped>
.status-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 300px;
  padding: 40px 20px;
  border-radius: var(--radius-lg);
}

.status-container.idle {
  background: var(--surface-card);
  color: var(--text-dim);
}

.status-container.loading {
  background: var(--surface-card);
  color: var(--text-secondary);
}

.status-container.failed {
  background: var(--error-bg);
  color: var(--error);
}

.status-icon {
  width: 48px;
  height: 48px;
}

.status-text {
  font-size: 15px;
  font-weight: 500;
}

.status-hint {
  font-size: 12px;
  color: var(--text-dim);
}

.status-timer {
  font-size: 12px;
  color: var(--primary);
  font-weight: 500;
}

.status-error {
  font-size: 12px;
  color: var(--error);
  max-width: 300px;
  text-align: center;
  word-break: break-word;
}

.retry-btn {
  padding: 8px 24px;
  border-radius: var(--radius-sm);
  background: var(--error);
  color: white;
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.2s;
}

.retry-btn:hover {
  opacity: 0.9;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--surface-elevated);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* Result area */
.result-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.image-wrapper {
  width: 100%;
  max-height: 500px;
  background: var(--surface-card);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.result-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* Revised prompt */
.revised-prompt {
  padding: 12px 16px;
  background: var(--surface-card);
  border-radius: var(--radius);
  border: 1px solid var(--border-light);
}

.revised-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.revised-text {
  font-size: 12px;
  color: var(--text-default);
  margin-top: 4px;
  line-height: 1.5;
}

/* Action buttons */
.image-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}

.download-btn {
  background: var(--primary);
  color: var(--text-on-primary);
}

.download-btn:hover {
  background: var(--primary-hover);
}

.regenerate-btn {
  background: var(--surface-input);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.regenerate-btn:hover {
  background: var(--surface-hover);
}

.btn-icon {
  width: 16px;
  height: 16px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
