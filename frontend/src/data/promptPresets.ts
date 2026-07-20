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

// ─── Cartoon presets (9) ──────────────────────────────────────────

export interface CartoonPreset {
  label: string;
  value: string;
  /** Short description displayed on the preset card */
  description: string;
}

export const cartoonPresets: CartoonPreset[] = [
  {
    label: "Q版贴纸+自定义表情",
    description: "生成四个表情贴纸：生气、嘟嘴、疑惑、发怒",
    value:
      "引用上面的图片人物造型，生成一套Q版贴纸，要有厚白边，必须要透明背景，生成四个表情图片，这四个表情分别是：生气，嘟嘴，疑惑，发怒。",
  },
  {
    label: "史努比风格",
    description: "史努比漫画风格贴纸头像",
    value:
      "学习史努比漫画风格，将照片中的人生成为此风格的贴纸头像。模仿形体，脸型，肤色、五官表情。图中人物面部装饰，发型以及发饰，服装，配饰、表情、姿势保持一致。背景白底，只要完整人物，确保最终图像看起来像史努比漫画风格的人物。",
  },
  {
    label: "皮克斯风格",
    description: "Pixar animation style",
    value: "Pixar animation style",
  },
  {
    label: "卡通头像",
    description: "圆角方形头像框，手绘粗线稿",
    value:
      "参考照片生成卡通头像，圆角方形头像框，白色贴纸描边，半身胸像，正面像，手绘粗线稿（深灰/黑），极简配色，空白底色，轻水彩上色与蜡笔/粉笔纹理，纸张颗粒噪点，干净留白，少量元素突破边框标志性元素/特效，可爱明快表情，柔和内阴影或投影，画面整洁、无复杂背景。",
  },
  {
    label: "卡通正面全身像",
    description: "1.5头身Q版萌系卡通比例，手绘插画风格",
    value:
      "将该人物改为卡通正面全身像，1.5头身的 Q 版萌系卡通比例，让身体宽度比头略宽。手绘插画风格，干净流畅的黑色轮廓线，平涂色彩，柔和渐变阴影，暖色调配色，温馨治愈的学院风。保留真人面部核心特征（眼镜、发型、脸型、五官比例，表情），亲切专业的神态，全身站立构图，保持照片中服饰，纯白色免扣背景，无多余装饰，突出人物主体，人物比例协调，五官可爱不失写实感，风格类似卡通群像。",
  },
  {
    label: "萌风Q版角色·涂鸦",
    description: "凌乱黑色线稿，粗笔触水粉蜡笔质感",
    value:
      "一个萌风Q版角色，凌乱粗糙的黑色线稿，幼态比例，像小孩随手涂鸦但极具设计感，粗笔触、水粉厚涂、蜡笔质感，边缘随意外扩，留白背景、可爱、手绘感极强，不精致，故意画歪，松散构图，低饱和奶油色调，艺术涂鸦插画",
  },
  {
    label: "Chibi风格",
    description: "Chibi画风表情包，白底完整人物",
    value:
      "将图片生成 chibi 画风表情包，背景白底，只要完整人物，互不遮挡，确保最终图像看起来是chibi风格的人物。",
  },
  {
    label: "猪猪boy/girl",
    description: "儿童蜡笔涂鸦插画，Q版萌系二次元，可爱混乱风",
    value:
      "把上传照片转化成一种可爱混乱的儿童蜡笔涂鸦插画风格。整体像是彩铅+蜡笔+手账贴纸+MS Paint涂鸦的结合。使用：粗糙线条，抖动边缘，不均匀上色，纸张纹理，彩铅叠色，蜡笔颗粒感，故意幼稚但很有灵气的画风。人物变成Q版萌系二次元风格，大眼睛，夸张表情，可爱活泼。背景加入大量doodle：爱心，星星，糖果，笑脸云朵，小花，贴纸，游戏U元素，乱涂乱画符号。颜色以：粉色，蓝色，紫色，黄色，薄荷色为主。整体氛围：可爱，混乱，梦幻，少女感，游戏宅手账风，互联网kawaii, Kawaiaesthetic不要精致，不要高级商业插画感，不要真实渲染，不要干净线稿，保留手绘失败感和乱涂鸦感",
  },
  {
    label: "像素风格",
    description: "Everskies像素画风贴纸头像",
    value:
      "学习everskies像素画风，将照片中的人生成为此风格的贴纸头像。模仿形体，脸部，五官表情，服饰和发型的画法。用附件图中人物的发型，衣服和配饰画一张人物插图，背景白底，只要完整人物，确保最终图像看起来像像素风格的人物。",
  },
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
