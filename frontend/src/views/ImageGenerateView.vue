<script setup lang="ts">
import ImageForm from "../components/ImageForm.vue";
import ImageResult from "../components/ImageResult.vue";
</script>

<template>
  <div class="generate-view">
    <!-- Left: Input Form -->
    <div class="form-panel">
      <ImageForm />
    </div>

    <!-- Right: Result Area -->
    <div class="result-panel">
      <div class="result-header">
        <h2 class="result-title">生成结果</h2>
      </div>
      <div class="result-content">
        <ImageResult />
      </div>
    </div>
  </div>
</template>

<style scoped>
.generate-view {
  display: flex;
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  min-height: calc(100vh - 64px);
}

.form-panel {
  flex: 0 0 420px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-sm);
  height: fit-content;
}

.result-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.result-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-light);
}

.result-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.result-content {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
}

/* Responsive: stack on narrow screens */
@media (max-width: 900px) {
  .generate-view {
    flex-direction: column;
    padding: 16px;
  }

  .form-panel {
    flex: none;
  }
}
</style>
