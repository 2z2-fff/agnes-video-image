<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { getDimensions } from "../data/promptPresets";

const props = defineProps<{
  mode: "image" | "video";
}>();

const emit = defineEmits<{
  apply: [prompt: string];
}>();

const showPanel = ref(false);

// Dimension values — keyed by dimension key
const dimensions = reactive<Record<string, string>>({
  subject: "",
  style: "",
  composition: "",
  lighting: "",
  color: "",
  mood: "",
  detail: "",
  motion: "",
  camera: "",
});

// Get dimension configs for current mode
const dimensionList = computed(() => getDimensions(props.mode));

// Combined prompt — joins non-empty dimension values with ", "
const combinedPrompt = computed(() => {
  const parts: string[] = [];
  for (const dim of dimensionList.value) {
    const val = dimensions[dim.key]?.trim();
    if (val) {
      parts.push(val);
    }
  }
  return parts.join("，");
});

// Select a preset option (toggle off if already selected)
function selectPreset(key: string, value: string) {
  if (dimensions[key] === value) {
    dimensions[key] = "";
  } else {
    dimensions[key] = value;
  }
}

// Apply combined prompt to the parent's prompt field
function applyPrompt() {
  if (combinedPrompt.value) {
    emit("apply", combinedPrompt.value);
  }
}

// Clear all dimensions
function clearAll() {
  for (const key of Object.keys(dimensions)) {
    dimensions[key] = "";
  }
}
</script>

<template>
  <div class="prompt-engineer">
    <!-- Toggle button (matches .advanced-toggle pattern) -->
    <button class="pe-toggle" @click="showPanel = !showPanel">
      <svg
        class="pe-chevron"
        :class="{ rotated: showPanel }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      提示词工程
    </button>

    <!-- Collapsible panel -->
    <div v-show="showPanel" class="pe-panel">
      <!-- Dimension fields -->
      <div
        v-for="dim in dimensionList"
        :key="dim.key"
        class="pe-section"
      >
        <label class="pe-label">{{ dim.label }}</label>

        <!-- Text input dimensions -->
        <input
          v-if="dim.type === 'text'"
          v-model="dimensions[dim.key]"
          class="pe-text-input"
          :placeholder="dim.placeholder"
        />

        <!-- Button group dimensions -->
        <div v-else class="pe-options">
          <button
            v-for="opt in dim.presets"
            :key="opt.value"
            :class="['pe-opt', { active: dimensions[dim.key] === opt.value }]"
            @click="selectPreset(dim.key, opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <!-- Preview area -->
      <div class="pe-preview">
        <label class="pe-label">预览</label>
        <div class="pe-preview-text">
          <span v-if="combinedPrompt">{{ combinedPrompt }}</span>
          <span v-else class="pe-preview-empty">填写维度后自动生成提示词...</span>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="pe-actions">
        <button class="pe-clear-btn" @click="clearAll">清空</button>
        <button
          class="pe-apply-btn"
          :disabled="!combinedPrompt"
          @click="applyPrompt"
        >
          应用到提示词
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prompt-engineer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Toggle button — matches .advanced-toggle from VideoForm */
.pe-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: color 0.2s;
}

.pe-toggle:hover {
  color: var(--primary);
}

.pe-chevron {
  width: 16px;
  height: 16px;
  transition: transform 0.2s;
}

.pe-chevron.rotated {
  transform: rotate(90deg);
}

/* Panel — matches .advanced-panel from VideoForm */
.pe-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--surface-card);
  border-radius: var(--radius);
  padding: 16px;
}

/* Dimension section */
.pe-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pe-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

/* Text input */
.pe-text-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg);
  transition: all 0.2s;
  box-sizing: border-box;
}

.pe-text-input::placeholder {
  color: var(--text-muted);
}

.pe-text-input:focus {
  outline: none;
  border-color: var(--primary);
}

/* Button group — 3-column grid */
.pe-options {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.pe-opt {
  padding: 6px 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg);
  text-align: center;
  transition: all 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pe-opt:hover {
  border-color: var(--primary-light);
  color: var(--primary);
}

.pe-opt.active {
  border-color: var(--primary);
  background: var(--primary-bg);
  color: var(--primary);
  font-weight: 500;
}

/* Preview area */
.pe-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pe-preview-text {
  padding: 10px 12px;
  background: var(--surface-input);
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-default);
  min-height: 44px;
  word-break: break-all;
}

.pe-preview-empty {
  color: var(--text-muted);
}

/* Action buttons */
.pe-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.pe-clear-btn {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg);
  transition: all 0.2s;
}

.pe-clear-btn:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
}

.pe-apply-btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-on-primary);
  background: var(--primary);
  transition: all 0.2s;
}

.pe-apply-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.pe-apply-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Responsive — 2 columns on narrow form panels */
@media (max-width: 480px) {
  .pe-options {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
