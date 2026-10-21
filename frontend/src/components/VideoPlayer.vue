<script setup lang="ts">
import { computed } from "vue";
import { useVideoStore } from "../stores/videoStore";
import type { AspectRatio } from "../api/video";

const store = useVideoStore();

// Map every aspect ratio the video API accepts to a CSS aspect-ratio value.
const aspectRatioCss: Record<AspectRatio, string> = {
  "21:9": "21 / 9",
  "16:9": "16 / 9",
  "4:3": "4 / 3",
  "1:1": "1 / 1",
  "3:4": "3 / 4",
  "9:16": "9 / 16",
};

const playerAspect = computed(() => aspectRatioCss[store.aspectRatio] ?? "16 / 9");
</script>

<template>
  <div class="video-result-area" v-if="store.isComplete && store.streamUrl">
    <div class="video-wrapper" :style="{ aspectRatio: playerAspect }">
      <video
        :src="store.streamUrl"
        controls
        autoplay
        class="video-player"
      >
        您的浏览器不支持视频播放
      </video>
    </div>

    <div class="video-actions">
      <a
        v-if="store.downloadUrl"
        :href="store.downloadUrl"
        class="action-btn download-btn"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <path d="M12 4v12M12 16l-4-4M12 16l4-4" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M4 20h16" stroke-linecap="round" />
        </svg>
        下载视频
      </a>
      <button class="action-btn regenerate-btn" @click="store.generate()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
          <path d="M4 4v6h6M20 20v-6h-6" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M4 10a8 8 0 0114-4l2 2M20 14a8 8 0 01-14 4l-2-2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        重新生成
      </button>
    </div>

    <div v-if="store.error" class="result-error">
      {{ store.error }}
    </div>
  </div>
</template>

<style scoped>
.video-result-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.video-wrapper {
  width: 100%;
  max-height: 400px;
  background: #000;
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.video-actions {
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

.result-error {
  padding: 8px 12px;
  background: var(--error-bg);
  color: var(--error);
  border-radius: var(--radius-sm);
  font-size: 12px;
}
</style>
