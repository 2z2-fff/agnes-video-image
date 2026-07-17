/**
 * Prompt Engineering Presets
 *
 * Multi-dimensional prompt building blocks for image and video generation.
 * Each preset has a Chinese label (for UI display) and a Chinese value (for the prompt).
 */

export interface PresetOption {
  /** UI display label */
  label: string;
  /** Value inserted into the combined prompt */
  value: string;
}

// ─── Image dimensions (7) ──────────────────────────────────────────

/** 风格 — Art style */
export const stylePresets: PresetOption[] = [
  { label: "水彩插画", value: "水彩插画风格" },
  { label: "油画", value: "油画风格" },
  { label: "摄影级", value: "摄影级真实感" },
  { label: "赛博朋克", value: "赛博朋克风格" },
  { label: "日系动漫", value: "日系动漫风格" },
  { label: "3D渲染", value: "3D渲染风格" },
  { label: "国风水墨", value: "中国水墨画风格" },
  { label: "像素艺术", value: "像素艺术风格" },
];

/** 构图 — Composition / framing */
export const compositionPresets: PresetOption[] = [
  { label: "特写", value: "特写构图" },
  { label: "半身", value: "半身构图" },
  { label: "全景", value: "全景构图" },
  { label: "俯视", value: "俯视角度" },
  { label: "仰视", value: "仰视角度" },
  { label: "对称", value: "对称构图" },
  { label: "三分法", value: "三分法构图" },
];

/** 光照 — Lighting */
export const lightingPresets: PresetOption[] = [
  { label: "清晨柔光", value: "清晨柔光" },
  { label: "逆光剪影", value: "逆光剪影" },
  { label: "工作室灯光", value: "工作室灯光" },
  { label: "自然光线", value: "自然光线" },
  { label: "霓虹灯光", value: "霓虹灯光" },
  { label: "柔和侧光", value: "柔和侧光" },
  { label: "黄金时刻", value: "黄金时刻光线" },
];

/** 色调 — Color palette */
export const colorPresets: PresetOption[] = [
  { label: "暖色调", value: "暖色调" },
  { label: "冷色调", value: "冷色调" },
  { label: "莫兰迪", value: "莫兰迪色系" },
  { label: "高饱和", value: "高饱和度色彩" },
  { label: "黑白", value: "黑白" },
  { label: "复古色调", value: "复古色调" },
];

/** 氛围 — Mood / atmosphere */
export const moodPresets: PresetOption[] = [
  { label: "温暖宁静", value: "温暖宁静的氛围" },
  { label: "神秘梦幻", value: "神秘梦幻的氛围" },
  { label: "活力四射", value: "充满活力的氛围" },
  { label: "忧郁沉静", value: "忧郁沉静的氛围" },
  { label: "史诗壮阔", value: "史诗壮阔的氛围" },
  { label: "清新日常", value: "清新日常的氛围" },
];

// ─── Video extra dimensions (+2) ───────────────────────────────────

/** 主体动作 — Subject motion */
export const motionPresets: PresetOption[] = [
  { label: "微微移动", value: "主体微微移动" },
  { label: "缓慢行走", value: "主体缓慢行走" },
  { label: "快速运动", value: "主体快速运动" },
  { label: "轻轻飘动", value: "主体轻轻飘动" },
  { label: "旋转", value: "主体旋转运动" },
  { label: "渐入渐出", value: "渐入渐出过渡" },
];

/** 镜头运动 — Camera movement */
export const cameraPresets: PresetOption[] = [
  { label: "固定", value: "镜头固定" },
  { label: "推进", value: "镜头缓慢推进" },
  { label: "拉远", value: "镜头拉远" },
  { label: "环绕", value: "镜头环绕" },
  { label: "跟随", value: "镜头跟随" },
  { label: "摇摄", value: "镜头摇摄" },
];

// ─── Dimension metadata (for rendering) ────────────────────────────

export interface DimensionConfig {
  key: string;
  label: string;
  type: "text" | "select";
  presets?: PresetOption[];
  placeholder?: string;
}

/** Image mode dimensions — ordered for prompt assembly */
export const imageDimensions: DimensionConfig[] = [
  { key: "subject", label: "主体描述", type: "text", placeholder: "描述你要生成的主体内容，如：一只柴犬坐在花园里" },
  { key: "style", label: "风格", type: "select", presets: stylePresets },
  { key: "composition", label: "构图", type: "select", presets: compositionPresets },
  { key: "lighting", label: "光照", type: "select", presets: lightingPresets },
  { key: "color", label: "色调", type: "select", presets: colorPresets },
  { key: "mood", label: "氛围", type: "select", presets: moodPresets },
  { key: "detail", label: "补充细节", type: "text", placeholder: "可选，如：精致纹理、毛发质感、花瓣上的露珠" },
];

/** Video-only extra dimensions — appended after image dimensions */
export const videoExtraDimensions: DimensionConfig[] = [
  { key: "motion", label: "主体动作", type: "select", presets: motionPresets },
  { key: "camera", label: "镜头运动", type: "select", presets: cameraPresets },
];

/** Get all dimensions for a given mode */
export function getDimensions(mode: "image" | "video"): DimensionConfig[] {
  if (mode === "video") {
    // Insert video extras before "detail" (last image dimension)
    const base = imageDimensions.slice(0, -1);
    const detail = imageDimensions.slice(-1);
    return [...base, ...videoExtraDimensions, ...detail];
  }
  return imageDimensions;
}
