# Agnes AI Generator（图片 + 视频）

基于 Agnes AI 官方 API 的图片与视频生成应用：Vue 3 + Vite 前端，FastAPI 后端。

- 图片：`agnes-image-2.5-flash`（文生图 / 图生图 / 卡通图像生成，所有档位当前免费）
- 视频：`agnes-video-2.5-flash`（默认，720P，当前 $0/s）/ `agnes-video-2.5`（720P–2K，按秒计费）

> 项目已从旧版 **Agnes Video V2.0** 参数体系（`width/height/num_frames/frame_rate`）迁移到
> **Agnes Video 2.5** 的 OpenAI Videos 兼容接口。旧参数会被服务端以 `400` 拒绝，
> 详见 [`FIXES.md`](./FIXES.md)。

## 快速开始

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
```

编辑 `backend/.env`：

```ini
AGNES_API_KEY=sk-your-key
AGNES_BASE_URL=https://apihub.agnes-ai.com
AGNES_VIDEO_MODEL=agnes-video-2.5-flash   # 或 agnes-video-2.5（付费，支持 1080P/1K/2K）
AGNES_IMAGE_MODEL=agnes-image-2.5-flash
UPLOADS_DIR=                              # 可选：生成图片的保存目录，默认 backend/uploads
```

启动：

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 <http://localhost:5173>（`/api` 与 `/uploads` 已代理到 8000 端口）。

### 3. 使用

1. 选择模式：文生视频 / 图生视频·首尾帧 / 多图参考（图片页：文生图 / 图生图 / 卡通）
2. 输入提示词，可选用 Prompt 工程助手
3. 选择宽高比（21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16）、时长（4–12 秒）、分辨率档位
4. 点击生成，等待队列与生成完成，视频自动播放

### 视频三种模式

| 模式 | 需要的素材 | API `mode` | 说明 |
| --- | --- | --- | --- |
| 文生视频 | 无 | `text` | 纯提示词生成 |
| 图生视频 / 首尾帧 | 首帧（必填）+ 尾帧（可选） | `keyframe` | 只传首帧=图生视频；再传尾帧=首尾过渡，成片首尾尽量贴合两张图 |
| 多图参考 | 1–N 张（2.5 最多 8，Flash 最多 5） | `reference` | 图片作内容/风格参考，成片可能重新构图；提示词用 `<Picture 1>`、`<Picture 2>` 指代 |

> 首帧/尾帧与多图参考**互斥**：API 不允许 `first_frame`/`last_frame` 与 `images` 同时出现，后端会提前用 422 拦下。

## 参数对照（官方 API）

| 项目 | 图片 API | 视频 API |
| --- | --- | --- |
| 端点 | `POST /v1/images/generations` | `POST /v1/videos` + `GET /agnesapi` |
| 模型 | `agnes-image-2.5-flash` | `agnes-video-2.5-flash` / `agnes-video-2.5` |
| 尺寸 | `size`: `1K/2K/3K/4K` + `ratio` | `size`: `720P/1080P/1K/2K` + `aspect_ratio` |
| 时长 | — | `seconds`: 字符串 `"4"`–`"12"` |
| 模式 | `extra_body.image[]` 表示图生图 | `mode`: `text` / `keyframe` / `reference` |
| 参考图 | URL 或 Data URI Base64 | `first_frame`（图生视频，实测可用 Data URI） |

## API 端点（本项目）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 当前模型与可用参数（前端据此渲染选项） |
| POST | `/api/generate` | 提交视频任务（`txt2vid` / `img2vid`） |
| GET | `/api/generate/{id}` | 查询状态 |
| GET | `/api/generate/{id}/wait` | 长轮询等待完成 |
| GET | `/api/generate/{id}/stream` | 视频流代理（支持 Range） |
| GET | `/api/generate/{id}/download` | 下载视频 |
| GET | `/api/history` | 最近生成记录（切换页面/刷新后可恢复） |
| DELETE | `/api/history/{id}` | 删除某条记录（文件保留） |
| POST | `/api/image/generate` | 图片生成（`txt2img` / `img2img` / `cartoon`） |

## 结果不会丢

- 生成完成后，视频会被**自动下载到 `backend/uploads/videos/`**，图片保存在 `backend/uploads/`；
- 每次生成都会写入 `backend/uploads/history.json`，前端在「最近生成」页可回看、播放、下载；
- 前端把最近一次结果与**未完成任务**的 `task_id` 存在 localStorage，刷新或切换页面后自动恢复，
  未完成的任务会用原 `task_id` **续查**（不会重复计费）。

## 测试

```bash
cd backend
python -u scripts/e2e_test.py          # 端到端：图生图 + 文生视频 + 图生视频
python -u scripts/probe_api.py fast    # 接口探测：模型/参数是否被接受
```

## 项目结构

```
Qoderwork/
├── backend/
│   ├── .env                    # API Key 与模型配置
│   ├── app/
│   │   ├── config.py           # 模型、档位、比例、重试等常量
│   │   ├── schemas.py          # 请求/响应模型（含校验）
│   │   ├── services/
│   │   │   ├── agnes_image.py  # 图片 API 封装
│   │   │   └── agnes_video.py  # 视频 API 封装（创建/轮询/代理）
│   │   └── api/                # REST 端点
│   └── scripts/                # 探测与端到端测试脚本
├── frontend/src/               # Vue 3 + Pinia + Axios
└── FIXES.md                    # 本次修复记录
```

## 技术栈

- 前端：Vue 3 + Vite + TypeScript + Pinia + Axios
- 后端：Python FastAPI + httpx + Pydantic v2 + Pillow
