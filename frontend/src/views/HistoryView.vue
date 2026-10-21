<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listHistory, deleteHistory, type HistoryRecord } from "../api/history";

const records = ref<HistoryRecord[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const filter = ref<"all" | "image" | "video">("all");

function videoSrc(rec: HistoryRecord): string | null {
  if (rec.local_url) return rec.local_url;
  if (rec.task_id) return `/api/generate/${rec.task_id}/stream`;
  if (rec.remote_url) return rec.remote_url;
  return null;
}

function timeLabel(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    records.value = await listHistory(100, filter.value === "all" ? undefined : filter.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载历史失败";
  } finally {
    loading.value = false;
  }
}

async function remove(rec: HistoryRecord) {
  try {
    await deleteHistory(rec.id);
    records.value = records.value.filter((r) => r.id !== rec.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "删除失败";
  }
}

onMounted(refresh);
</script>

<template>
  <div class="history-view">
    <div class="history-toolbar">
      <h2 class="title">最近生成</h2>
      <div class="toolbar-right">
        <div class="filter-group">
          <button
            v-for="f in (['all', 'image', 'video'] as const)"
            :key="f"
            :class="['filter-btn', { active: filter === f }]"
            @click="filter = f; refresh()"
          >
            {{ f === "all" ? "全部" : f === "image" ? "图片" : "视频" }}
          </button>
        </div>
        <button class="refresh-btn" :disabled="loading" @click="refresh">
          {{ loading ? "加载中..." : "刷新" }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>

    <p v-if="!loading && records.length === 0" class="empty-text">
      还没有生成记录。生成完成后会自动保存在这里，切换页面或刷新都不会丢。
    </p>

    <div class="history-grid">
      <div v-for="rec in records" :key="rec.id" class="history-card">
        <div class="thumb">
          <template v-if="rec.kind === 'video'">
            <video
              v-if="videoSrc(rec)"
              :src="videoSrc(rec) || ''"
              controls
              preload="metadata"
              class="media"
            ></video>
            <div v-else class="media fallback">视频未就绪</div>
          </template>
          <template v-else>
            <img v-if="rec.local_url" :src="rec.local_url" alt="生成图片" class="media" />
            <div v-else class="media fallback">图片缺失</div>
          </template>
        </div>

        <div class="meta">
          <span class="badge">{{ rec.kind === "video" ? "视频" : "图片" }}</span>
          <span class="time">{{ timeLabel(rec.created_at) }}</span>
          <span v-if="rec.status && rec.status !== 'completed'" class="status">{{ rec.status }}</span>
        </div>
        <p class="prompt" :title="rec.prompt">{{ rec.prompt || "（无提示词）" }}</p>

        <div class="actions">
          <a
            v-if="rec.local_url"
            :href="rec.local_url"
            :download="`${rec.kind}-${rec.id}`"
            class="link"
          >下载</a>
          <span v-if="!rec.local_url && rec.remote_url" class="hint">未落盘</span>
          <button class="delete-btn" @click="remove(rec)">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.history-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
  flex-wrap: wrap;
}

.title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-group {
  display: flex;
  background: var(--surface-input);
  border-radius: var(--radius);
  padding: 3px;
}

.filter-btn {
  padding: 6px 14px;
  border-radius: 7px;
  font-size: 12px;
  color: var(--text-secondary);
}

.filter-btn.active {
  background: var(--bg);
  color: var(--primary);
  box-shadow: var(--shadow-sm);
}

.refresh-btn {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg);
}

.error-text {
  color: var(--danger, #d33);
  font-size: 13px;
  margin-bottom: 12px;
}

.empty-text {
  color: var(--text-dim);
  font-size: 13px;
  padding: 40px 0;
  text-align: center;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.history-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.thumb {
  background: var(--surface-card);
  aspect-ratio: 16 / 9;
  display: flex;
  align-items: center;
  justify-content: center;
}

.media {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.fallback {
  font-size: 12px;
  color: var(--text-dim);
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 4px;
}

.badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--primary-bg);
  color: var(--primary);
}

.time,
.status {
  font-size: 11px;
  color: var(--text-dim);
}

.prompt {
  padding: 0 12px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: 36px;
}

.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 12px;
}

.link {
  font-size: 12px;
  color: var(--primary);
}

.hint {
  font-size: 11px;
  color: var(--text-dim);
}

.delete-btn {
  font-size: 12px;
  color: var(--text-dim);
}

.delete-btn:hover {
  color: var(--danger, #d33);
}
</style>
