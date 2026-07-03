<script setup lang="ts">
import { useVideoStore } from "../stores/videoStore";

const store = useVideoStore();

function formatTime(sec: number): string {
  if (sec < 60) return `${sec}秒`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}分${s}秒`;
}
</script>

<template>
  <!-- Idle state -->
  <div v-if="store.taskStatus === 'idle'" class="status-container idle">
    <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M10 9l5 3-5 3V9z" fill="currentColor" stroke="none" />
    </svg>
    <p class="status-text">填写参数后点击生成视频</p>
  </div>

  <!-- Queued state -->
  <div v-else-if="store.taskStatus === 'queued'" class="status-container loading">
    <div class="loading-spinner"></div>
    <p class="status-text">正在提交任务...</p>
  </div>

  <!-- Processing state -->
  <div v-else-if="store.taskStatus === 'in_progress'" class="status-container loading">
    <div class="loading-spinner"></div>
    <p class="status-text">视频生成中...</p>
    <p class="status-hint">预计需要 1-5 分钟</p>
    <p v-if="store.elapsedSec > 0" class="status-timer">已等待 {{ formatTime(store.elapsedSec) }}</p>
  </div>

  <!-- Failed / Timeout state -->
  <div v-else-if="store.isFailed" class="status-container failed">
    <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4M12 16h.01" stroke-linecap="round" />
    </svg>
    <p class="status-text">{{ store.taskStatus === 'timeout' ? '生成超时' : '生成失败' }}</p>
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

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
