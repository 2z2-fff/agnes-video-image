<script setup lang="ts">
import { ref } from "vue";
import GenerateView from "./views/GenerateView.vue";
import ImageGenerateView from "./views/ImageGenerateView.vue";

type ViewName = "video" | "image";
const currentView = ref<ViewName>("video");

const navItems: { key: ViewName; label: string; icon: string }[] = [
  {
    key: "video",
    label: "视频生成",
    icon: "M2 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM22 8l-4 4 4 4V8z",
  },
  {
    key: "image",
    label: "图片生成",
    icon: "M3 3h18v18H3V3zM8 6a2 2 0 100 4 2 2 0 000-4zM21 15l-5-5L5 21",
  },
];
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="header-content">
        <div class="logo">
          <svg class="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="logo-text">Agnes AI Generator</span>
        </div>
      </div>
    </header>

    <div class="app-body">
      <aside class="sidebar">
        <nav class="sidebar-nav">
          <button
            v-for="item in navItems"
            :key="item.key"
            :class="['nav-item', { active: currentView === item.key }]"
            @click="currentView = item.key"
          >
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path :d="item.icon" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="nav-label">{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <main class="app-main">
        <GenerateView v-if="currentView === 'video'" />
        <ImageGenerateView v-else-if="currentView === 'image'" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  background: var(--bg);
}

.app-header {
  height: 64px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  position: sticky;
  top: 0;
  z-index: 10;
}

.header-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 100%;
  display: flex;
  align-items: center;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  width: 24px;
  height: 24px;
  color: var(--primary);
}

.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

/* Sidebar layout */
.app-body {
  display: flex;
  min-height: calc(100vh - 64px);
}

.sidebar {
  flex: 0 0 200px;
  border-right: 1px solid var(--border);
  background: var(--surface-card);
  padding: 16px 12px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
  width: 100%;
  text-align: left;
}

.nav-item:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--primary-bg);
  color: var(--primary);
  font-weight: 600;
}

.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

.nav-label {
  white-space: nowrap;
}

.app-main {
  flex: 1;
  min-width: 0;
}

/* Responsive: hide sidebar on narrow screens */
@media (max-width: 768px) {
  .app-body {
    flex-direction: column;
  }

  .sidebar {
    flex: 0 0 auto;
    border-right: none;
    border-bottom: 1px solid var(--border);
    padding: 8px 12px;
  }

  .sidebar-nav {
    flex-direction: row;
    gap: 8px;
  }

  .nav-item {
    flex: 1;
    justify-content: center;
  }
}
</style>
