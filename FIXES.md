# Agnes AI Generator 修复记录

> 依据：Agnes AI 官方文档（2026-10 检索）
> · 视频：<https://agnes-ai.com/zh-Hans/docs/agnes-video-25>、<https://agnes-ai.com/zh-Hans/docs/agnes-video-25-flash>
> · 图片：<https://wiki.agnes-ai.com/en/docs/agnes-image-25-flash>
> · 定价：<https://wiki.agnes-ai.com/en/docs/pricing>
>
> 说明：服务端高负载（队列满）是本次测试中反复出现的**外部因素**，与代码缺陷需分开阅读，
> 详见第五节。

---

## 一、问题总览

原项目基于 **Agnes Video V2.0** 旧接口（`width` / `height` / `num_frames` / `frame_rate`），
而官方已升级为 **Video 2.5**（OpenAI Videos 兼容）。旧参数会被服务端**直接以 400 拒绝**，
因此视频功能处于完全不可用状态。图片功能可用，但尺寸档位与官方口径不一致（像素值会被静默归一化）。

实测证据（`scripts/probe_api.py`）：

```text
POST /v1/videos  {model: agnes-video-2.5-flash, width: 1152, height: 648, num_frames: 121, frame_rate: 24}
→ HTTP 400  {"code":"invalid_request","message":"width is a forbidden field",
             "data":{"param":"width"}}
```

| # | 严重度 | 问题 | 后果 |
|---|--------|------|------|
| 1 | 阻断 | 视频请求仍发 `width/height/num_frames/frame_rate` | 所有视频生成 400 失败 |
| 2 | 阻断 | 模型 ID 为 `agnes-video-v2.0` | 已被 2.5 取代，文档索引中已移除 |
| 3 | 阻断 | 轮询不带 `model_name` | `keyframe`/`reference` 任务查不到结果 |
| 4 | Bug | 提取结果 URL 时优先读 `remixed_from_video_id` | 可能把**视频 ID**当成 URL 返回 |
| 5 | Bug | 图生视频走 V2.0 的 `extra_body.image` 通道 | 2.5 需 `mode:keyframe` + `first_frame` |
| 6 | Bug | 发送 `negative_prompt` / `num_inference_steps` | 2.5 无前者、明确禁止后者 |
| 7 | 健壮性 | 轮询遇到一次网络瞬断即判定任务失败 | 已提交（可能已计费）的任务被丢弃 |
| 8 | 健壮性 | 队列满只重试 5×15s | 实测排队可达 7 分钟以上，几乎必然失败 |
| 9 | 正确性 | 图片尺寸用 `3840x2160` 等像素值 | 服务端静默归一化，出图尺寸与预期不符 |
| 10 | 正确性 | 图片模型仍为 `agnes-image-2.1-flash` | 可升级到 2.5（参数/价格相同，质量更高） |
| 11 | UX | 时长选项 3/5/10/17 秒 | 官方仅支持 **4–12 秒**，3s/17s 必失败 |
| 12 | UX | 宽高比仅 4 种、`VideoPlayer` 映射不全 | 缺 21:9 / 3:4，且新增比例会触发类型错误 |
| 13 | 环境 | `uploads/` 目录不可写 | 生成的图片无法落盘（PermissionError） |
| 14 | 环境 | 工作区目录缺 `WRITE_OWNER` | 沙箱无法为工作区授权，任何命令都跑不起来 |

---

## 二、逐项修复

### 1. 视频请求参数迁移到 2.5（`app/services/agnes_video.py`）

```diff
- body = {
-     "model": AGNES_MODEL,
-     "prompt": req.prompt,
-     "width": width, "height": height,
-     "num_frames": num_frames, "frame_rate": req.fps,
- }
+ body = {
+     "model": VIDEO_MODEL,
+     "prompt": _build_prompt(req),
+     "mode": _api_mode(req),           # txt2vid -> "text"，img2vid -> "keyframe"
+     "seconds": str(req.seconds),      # 字符串 "4"-"12"
+     "size": req.size,                 # "720P" | "1080P" | "1K" | "2K"
+     "aspect_ratio": req.aspect_ratio,
+ }
```

删除了 `_frames_for_duration()`（`8n+1` 帧数换算）与 `ASPECT_MAP`（像素尺寸表）——
2.5 不接受像素值与帧数，改由 `size` + `aspect_ratio` 决定输出。

### 2. 模型 ID 与配置（`app/config.py` / `.env`）

| 配置项 | 原值 | 新值 |
| --- | --- | --- |
| `AGNES_MODEL` | `agnes-video-v2.0` | 改为 `AGNES_VIDEO_MODEL=agnes-video-2.5-flash` |
| 图片模型 | `agnes-image-2.1-flash` | `AGNES_IMAGE_MODEL=agnes-image-2.5-flash` |

`agnes-video-2.5-flash` 当前 **$0/秒**且仅支持 720P，作为默认值可零成本跑通；
需要 1080P/1K/2K 时改为 `agnes-video-2.5`（按秒计费）。配置不匹配时后端直接给出可执行提示：

```json
{"detail":"agnes-video-2.5-flash 仅支持 size=720P（请求为 1080P）。
 如需 1080P/1K/2K，请把后端 .env 中的 AGNES_VIDEO_MODEL 设为 agnes-video-2.5（按秒计费）。"}
```

### 3. 轮询必须带 `model_name`

```diff
- params={"video_id": task_id}
+ params={"video_id": video_id, "model_name": VIDEO_MODEL}
```

官方：不带 `model_name` 的查询**仅适用于 `mode:"text"`**；本项目所有模式统一带上。

### 4. 结果 URL 提取顺序（真实 Bug）

```diff
- video_url = (
-     data.get("remixed_from_video_id")      # 这是视频 ID，不是 URL
-     or data.get("video_url") or data.get("url") ...
- )
+ video_url = data.get("url") or data.get("video_url") or data.get("output_url")
```

官方完成响应中结果是**顶层 `url`**。原代码把 `remixed_from_video_id` 放第一位，
遇到 remix 任务会把 ID 字符串当播放地址返回。

### 5. 图生视频改用 `keyframe` + `first_frame`

原先的通道是 V2.0 的 `extra_body.image = [base64]`。2.5 的等价能力是
`mode: "keyframe"` + `first_frame`。**实测 `first_frame` 接受 PNG Data URI**，
因此不需要为上传图片准备公网图床（官方案例用的是公网 URL，未写明 Base64 可用，本次已实测确认）：

```diff
- body["extra_body"] = {"image": [pure_b64]}
+ body["mode"] = "keyframe"
+ body["first_frame"] = _ensure_png_data_uri(req.image)   # data:image/png;base64,...
```

### 6. 移除 2.5 不支持的字段

- `num_inference_steps`：官方列为**禁止字段**，一律移除（UI 的"推理步数"滑块同步删除）。
- `negative_prompt`：2.5 无此参数，改为拼接到提示词末尾 `Avoid the following: ...`，
  保留用户意图而不触发 400。

### 7. 轮询抗瞬断（真实 Bug，测试中实地触发）

测试时轮询直接崩溃：

```text
httpx.RemoteProtocolError: Server disconnected without sending a response.
```

原实现一次异常就终止整个任务。修复分两层：

- `query_task_status()` 对 `httpx.TransportError`（超时/断连/协议错误）重试 3 次；
- `poll_until_complete()` 容忍 **连续 5 次**查询失败（429/502/503/504）后仍继续轮询，
  因为任务在服务端仍在跑，甚至可能已计费。

### 8. 队列满的重试预算（基于实测）

| 端点 | 实测现象 | 修复 |
| --- | --- | --- |
| 视频 | `503 video_queue_full`，连续重试 **21 次（约 7 分钟）**才被接受 | 重试 30 × 15s（≈7.5 分钟），超时给出中文说明 |
| 图片 | `503 image queue is full, please retry later` | 重试 8 × 20s |

### 9. 图片尺寸：像素值 → 档位 + 比例

官方明确：`1920x1080`、`3840x2160` 等**不是原生输出尺寸**，会被归一化
（例如 16:9 的 1K 实际是 `1312x736`）。原项目直接传 `3840x2160`，用户拿到的并非 4K 16:9。

```diff
- body = {"model": IMAGE_MODEL, "prompt": ..., "size": "3840x2160"}
+ body = {"model": IMAGE_MODEL, "prompt": ..., "size": "2K", "ratio": "16:9",
+         "extra_body": {"response_format": "url"}}
```

前端改为"分辨率档位 + 画幅比例"两组按钮，并按官方尺寸表实时显示真实输出尺寸
（如 `1K + 16:9 → 1312×736`）。

### 10. 新增 `GET /api/config`

前端据此只展示当前模型真正支持的组合（Flash 只给 720P），避免用户选到必然 400 的参数。

### 11. 前端同步

| 文件 | 修改 |
| --- | --- |
| `api/video.ts` | `seconds`/`size` 取代 `duration`/`fps`；比例扩展为 6 种；新增 `getAppConfig()` |
| `stores/videoStore.ts` | 新增 `size`、`seconds`、`availableSizes`（来自 `/api/config`），删除 `fps`/`inferenceSteps` |
| `components/VideoForm.vue` | 时长改为 4/5/6/8/10/12；新增分辨率档位；删除推理步数；Flash 限制提示 |
| `api/image.ts` / `stores/imageStore.ts` | `size` 改档位、新增 `ratio`；内置官方尺寸表 |
| `components/ImageForm.vue` | 档位 + 比例选择，显示真实输出尺寸 |
| `components/VideoPlayer.vue` | 补齐 6 种比例映射（原缺失导致 `TS7053` 编译错误） |
| `components/ImageResult.vue` | 比例改为按 `ratio` 映射（原按像素尺寸，已失效） |
| `components/StatusIndicator.vue` | 排队状态提示（队列满可能等待数分钟） |

### 12. 上传目录可配置

```diff
- UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
+ UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR") or (Path(__file__).parent.parent / "uploads")).resolve()
```

用于容器只读卷、受限沙箱等场景。

### 13. 环境层：Windows 文件权限

进项目时 shell 完全不可用：

```text
Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(E:\桌面文件\agnes_project)
```

根因：工作区目录缺少当前用户的 `WRITE_OWNER`，沙箱无法完成授权。
用 DSH 的文件权限诊断脚本修复，共 **3 个目录**（`agnes_project`、`Qoderwork`、`backend`、`uploads`），
全部 `verification: verified`，并各自留有回滚脚本于 `E:\桌面文件\agnes_acl_recovery\`。

---

## 三、测试环境与方法

- 后端：`uvicorn app.main:app --port 8000`（FastAPI），Python 3.12
- 前端：`npm run typecheck`（vue-tsc）
- 测试脚本：`backend/scripts/e2e_test.py`、`probe_api.py`、`probe_video.py`
- 全部使用**免费模型**：`agnes-video-2.5-flash`（$0/s）、`agnes-image-2.5-flash`（$0）

---

## 四、测试结果

端到端脚本 `scripts/e2e_test.py`（跑在真实后端 + 真实 Agnes API 上）：

```text
===== SUMMARY =====
PASS  image-to-image: /uploads/generated-2017e2665917.png bytes=1301367
PASS  text-to-video:  range=206/1024B  download=200/2032302B
PASS  image-to-video: url=https://platform-outputs.agnes-ai.space/videos/agnes-video-2.5/task_mglLK...mp4
exit code 0
```

| # | 用例 | 请求 | 结果 | 证据 |
|---|------|------|------|------|
| 1 | 文生图 | `txt2img`, `size=1K`, `ratio=16:9` | ✅ PASS | 输出 **1312×736**，与官方尺寸表一致 |
| 2 | 文生图 | `txt2img`, `size=2K`, `ratio=21:9` | ✅ PASS | 输出 **3136×1344**，与官方尺寸表一致 |
| 3 | 图生图 | `img2img`, `size=1K`, `ratio=16:9` | ✅ PASS | `/uploads/generated-2017e2665917.png`，1,301,367 B，PNG 校验通过 |
| 4 | 文生视频 | `txt2vid`, `4s`, `720P`, `16:9` | ✅ PASS | `task_vzDZ...` → completed；流 `206` + `Content-Range: bytes 0-1023/2032302`；下载 **2,032,302 B**，`ftypisom` |
| 5 | 图生视频 | `img2vid`（keyframe + PNG Data URI） | ✅ PASS | `task_mglL...` → completed，返回 `.../task_mglL....mp4` |
| 6 | 参数校验 | Flash 模型 + `size=1080P` | ✅ 正确拒绝 | `400`：提示改用 `agnes-video-2.5` 才支持 1080P/1K/2K |
| 7 | 参数校验 | `img2vid` 未传图片 | ✅ 正确拒绝 | `400`：img2vid 模式需要上传参考图片 |
| 8 | 参数校验 | `seconds=20` / `aspect_ratio=auto` | ✅ 正确拒绝 | `422`（Pydantic 白名单校验） |
| 9 | 前端类型检查 | `npm run typecheck` | ✅ PASS | `vue-tsc --noEmit` 无报错（修复前有 `TS7053`） |
| 10 | 配置接口 | `GET /api/config` | ✅ PASS | 正确返回当前模型与可用档位/比例 |
| 11 | 默认配置落盘 | 不设 `UPLOADS_DIR`，跑 `backend/uploads` | ✅ PASS | `generated-d6a97711b900.png`，834,634 B（证明 #13 的失败纯属沙箱，非代码缺陷） |

**关键实测结论（影响实现方案）**

1. **`first_frame` 接受 PNG Data URI**：官方示例只用公网 URL，未写明 Base64 可用。
   实测把 512×512 PNG 转成 `data:image/png;base64,...` 后直接建单成功并出片，
   因此图生视频**不需要**额外部署图床。
2. **视频任务完成响应的结果在顶层 `url`**：形如
   `https://platform-outputs.agnes-ai.space/videos/agnes-video-2.5/<task_id>.mp4`，
   且该域名**不能带 Bearer Token**（否则 401）。
3. **查询接口会返回 `429`**（实测每 15 秒查一次也会偶发命中），已加入 10 秒退避与
   20 次连续容错，避免长任务因限流被误判失败。
4. **轮询会偶发 `RemoteProtocolError`（服务端直接断连）**，已加传输层重试。
5. **状态机存在文档未列出的 `pending`**：官方只列 `queued/in_progress/completed/failed`，
   实测排队期返回 `pending` 且 `progress=0`，代码按"未完成"处理，不能只认 `queued/in_progress`。

---

## 五、外部因素（非代码缺陷，但影响体验）

1. **视频队列全局串行**：同一时间只允许 1 个视频任务，实测 `video_queue_full` 可持续 7 分钟以上，
   一次 keyframe 任务从创建到完成约 **20 分钟**（其中大部分时间在排队）。
2. **图片队列同样会满**：`image queue is full, please retry later`，文生图与图生图共用队列，
   实测图生图需要 4 轮重试（每轮含 8 次内部重试）才成功。
3. **轮询会偶发断连**：`Server disconnected without sending a response`，
   已在代码中重试，属于服务端行为。

> 建议：生产环境把视频任务做成「提交 → 后台轮询 → 通知」的异步流程，不要让 HTTP 请求阻塞等待排队。

---

## 六、遗留与建议

| 事项 | 说明 |
| --- | --- |
| 1K 画幅歧义 | 文档说 `1K` 固定 `1024x1024`，但又与 1080P 同价、共用画幅表。视频侧若选 `1K` 输出形状需实测确认 |
| 输出音轨 | **已确认**：成片带 AAC 32kHz 立体声音轨（见第 7.4 节），2.5 原生音画同步 |
| 输出分辨率与文档不符 | 文档写 720P+16:9 = `1280x720`，实测 keyframe 为 `1216x704`、reference 为 `1280x720`。尺寸随模式浮动，下游请读实际分辨率而非硬编码 |
| 付费模型未验证 | `agnes-video-2.5`（1080P/2K）会产生费用，本次未测，仅验证了参数校验与 720P 通路 |
| v2.0 存量调用 | 旧接口参数已被服务端拒绝，如有其他脚本仍用 `num_frames`，需一并迁移 |
| 沙箱写入限制 | 本会话的受限沙箱无法写入项目子目录，测试期间用 `UPLOADS_DIR` 指向可写目录；已单独用完整权限验证默认 `backend/uploads` 正常落盘（见测试用例 11），正常运行时无需任何覆盖 |

---

## 七、增量更新：首尾帧 + 多图参考（v2.1.0）

### 7.1 背景

此前图生视频只走 `keyframe` + `first_frame`，**最多 1 张图**。按官方能力补齐两项：

| 能力 | API 用法 | 图片数 |
| --- | --- | --- |
| 首尾帧 | `mode=keyframe` + `first_frame` + `last_frame` | 最多 2 张 |
| 多图参考 | `mode=reference` + `images[]` | 2.5 最多 8 张，Flash 最多 5 张 |

### 7.2 改动

**后端**

| 文件 | 改动 |
| --- | --- |
| `schemas.py` | `GenerateMode` 增加 `reference`；`GenerateRequest` 增加 `last_image`、`images[]`；新增 `model_validator` 强制三种模式的媒体互斥 |
| `services/agnes_video.py` | `_api_mode` 三路映射；`_build_body` 支持 `last_frame` 与 `images`（逐张转 PNG Data URI）；`_validate_model_and_size` 增加参考图上限校验 |
| `config.py` | 新增 `FLASH_MAX_IMAGES=5` 与 `max_reference_images()`，按模型返回上限 |
| `main.py` | `/api/config` 增加 `modes`、`supports_last_frame`、`max_reference_images` |

**前端**

| 文件 | 改动 |
| --- | --- |
| `api/video.ts` | 模式类型加 `reference`；请求体加 `last_image` / `images`；`AppConfig` 补三个新字段 |
| `stores/videoStore.ts` | 新增尾帧与参考图状态、多文件上传/删除、上限判断、切换模式时互斥清理 |
| `components/VideoForm.vue` | 三个 tab；首帧/尾帧双槽位；参考图网格（`Picture N` 角标、可增删、显示剩余配额） |

### 7.3 互斥规则（后端提前拦截，不依赖服务端 400）

| 组合 | 结果 |
| --- | --- |
| `reference` + `first_frame` | `422` 多图参考不能同时使用首帧/尾帧 |
| `txt2vid` + 任何图片 | `422` 文生视频不接受参考图片 |
| `img2vid` 缺首帧 | `422` 图生视频需要上传首帧图片 |
| `reference` 无图片 | `422` 至少需要 1 张 |
| `reference` 6 张（Flash 上限 5） | `400` 并提示切换到 `agnes-video-2.5` 可用 8 张 |

### 7.4 验证状态

`scripts/e2e_multimodal.py`：

```text
=== Phase 0: validation ===
PASS  reference + first_frame 被拒绝: HTTP 422
PASS  txt2vid + images 被拒绝: HTTP 422
PASS  img2vid 缺首帧被拒绝: HTTP 422
PASS  reference 缺图片被拒绝: HTTP 422
PASS  reference 6 张（Flash 上限 5）被拒绝: HTTP 400
```

**请求体结构已验证**（后端构造出的 body）：

```text
首尾帧   keys=[model, prompt, mode, seconds, size, aspect_ratio, first_frame, last_frame]
多图参考 keys=[model, prompt, mode, seconds, size, aspect_ratio, images]  count=2
```

**出片验证：全部通过**

```text
===== SUMMARY (exit code 0) =====
PASS  reference + first_frame 被拒绝: HTTP 422
PASS  txt2vid + images 被拒绝: HTTP 422
PASS  img2vid 缺首帧被拒绝: HTTP 422
PASS  reference 缺图片被拒绝: HTTP 422
PASS  reference 6 张（Flash 上限 5）被拒绝: HTTP 400
PASS  首尾帧: task_dNIeD73kEnCsuYDbbBQ0xCLlA8av9R9Y.mp4
PASS  多图参考(2张): task_4yNjwlciXIna1Ql0A67wW1AHRdpD9gRz.mp4
```

**抽帧视觉验证**（用 ffmpeg 从成片抽帧，确认不是"只要完成就算过"）：

| 模式 | 输入 | 成片实际画面 | 结论 |
| --- | --- | --- | --- |
| 首尾帧 | 首帧=红色 `START` 边框图；尾帧=蓝色 `END` 边框图 | 第 1 帧 = 红色 START 图；末帧 = 蓝色 END 图 | `first_frame` / `last_frame` **真实生效**，构图被锁定 |
| 多图参考 | `<Picture 1>`=黄色；`<Picture 2>`=蓝色 | 黄色衣着的角色站在蓝色环境光场景中 | `images[]` **真实生效**，两张图分别映射到"角色"与"场景" |

**输出规格实测**

| 模式 | 时长 | 分辨率 | 音轨 |
| --- | --- | --- | --- |
| 首尾帧（keyframe） | 4.46s | 1216×704 | AAC 32kHz 立体声 |
| 多图参考（reference） | 4.48s | **1280×720** | AAC 32kHz 立体声 |

> 注意：同样请求 `size=720P&aspect_ratio=16:9`，keyframe 输出 1216×704、reference 输出 1280×720。
> 说明**实际输出尺寸随模式/内容浮动**，不要按文档的 `1280x720` 硬编码下游处理。
>
> 另外两者都**带音轨**（AAC 立体声），即 2.5 是原生音画同步，修正了本文档早前"是否带音轨未知"的遗留项。

### 7.5 其它

- 前端 `vue-tsc --noEmit` 通过（含新增的三种模式与多图状态）。
- 提示词可用 `<Picture N>` 指代素材，前端会按已上传数量实时提示；后端在未检测到占位符时记一条 warning（不阻断）。

---

## 八、修复：切换页面丢失已生成/生成中的资源（v2.2.0）

### 8.1 现象

生成图片或视频后切换页面，结果消失；生成中的任务也随之丢失；并且**没有任何保存**。

### 8.2 根因

不是路由问题（导航是 `v-if`，整个过程没有调用 `reset()`，单次会话内 Pinia 状态本可保留），而是**持久化完全缺失**：

| # | 根因 | 后果 |
| --- | --- | --- |
| 1 | 结果只存在 Pinia 内存里，没有 `localStorage` | 刷新、HMR 重载、任何重建 store 的动作都会清空 |
| 2 | 后端**从不保存视频文件**，只返回 Agnes 的临时 URL + task_id | 一旦前端忘了 task_id，产物就再无入口 |
| 3 | 生成中的任务没有记录 | 关页面/刷新后无法续查，任务变成"孤儿" |
| 4 | 图片虽已落盘 `uploads/`，但没有任何索引 | 文件在，UI 里找不回来 |

### 8.3 修复

**后端**

| 文件 | 改动 |
| --- | --- |
| `app/history.py`（新增） | `uploads/history.json` 记录每次生成：id / kind / 时间 / 状态 / prompt / 参数 / `local_url` / `remote_url`；线程锁 + 原子写；最多保留 200 条 |
| `app/services/agnes_video.py` | 建单成功即写记录（含 `task_id`）；任务完成时把 mp4 下载到 `uploads/videos/<task_id>.mp4` 并回填 `local_url`；**自愈**：终态但无记录的任务自动补一条 |
| `app/services/agnes_image.py` | 图片保存后写记录，响应返回 `record_id` |
| `app/api/history.py`（新增） | `GET /api/history`、`GET /api/history/by-task/{task_id}`、`DELETE /api/history/{id}` |
| `app/config.py` | `VIDEO_DIR`、`HISTORY_FILE`；`ensure_dirs()` 失败**只记录不抛异常** |

**前端**

| 文件 | 改动 |
| --- | --- |
| `lib/persist.ts`（新增） | localStorage 封装，命名空间 + 静默失败（隐私模式/配额不报错） |
| `stores/videoStore.ts` | 建单即把 `taskId` 存入 localStorage；完成后存结果；`restore()` 恢复上次结果，**未完成任务自动续查**；`loadFromHistory()` |
| `stores/imageStore.ts` | 完成后持久化结果，`restore()` 恢复 |
| `views/HistoryView.vue`（新增） | "最近生成"页：图片/视频网格、筛选、内联播放、下载、删除 |
| `App.vue` | 新增第三个导航；启动时调用两个 store 的 `restore()` |

### 8.4 关键设计取舍

1. **落盘优先于远程 URL**：完成后即把 mp4 下载到本地，播放优先用 `/uploads/videos/...` —— Agnes 的链接会过期，本地副本不会。
2. **持久化是"尽力而为"**：`ensure_dirs()` 与 `history._write()` 都吞掉 `OSError` 并记 warning。
   这点在测试中真实触发过——目录不可写时旧代码会让**整个应用启动失败**，现在只降级为"无历史"。
3. **续查而非重跑**：恢复时若任务未完成，用原 `task_id` 继续轮询，不会重复计费。

### 8.5 验证

```text
# 1) 旧任务（建于功能上线前）查询后自动落盘 + 自愈入历史
GET /api/generate/task_dNIeD...  → local_url=/uploads/videos/task_dNIeD....mp4
GET /uploads/videos/task_dNIeD....mp4 → 200 video/mp4, 1,177,704 B

# 2) 新图片生成写入历史
POST /api/image/generate → {"image_url":"/uploads/generated-a0de85b60bf0.png","record_id":"8b6e5d3dc408"}

# 3) 历史列表（经前端 5173 代理）
GET /api/history → count=2
  [image] completed local=/uploads/generated-a0de85b60bf0.png
  [video] completed local=/uploads/videos/task_dNIeD....mp4

# 4) uploads/history.json 已生成（992 bytes）

# 5) 前端编译
App.vue / HistoryView.vue / videoStore.ts / api/history.ts / lib/persist.ts 均 200
vue-tsc --noEmit 通过
```

### 8.6 遗留

| 事项 | 说明 |
| --- | --- |
| 历史记录无分页 | 最多保留 200 条，超出按时间淘汰；量大后需要分页或迁移到数据库 |
| 删除记录不删文件 | `DELETE /api/history/{id}` 只移除索引，`uploads/` 里的文件保留，需要时另做清理 |
| 视频落盘占磁盘 | 每条视频约 0.3–3 MB，长期运行需定期清理 `uploads/videos` |
