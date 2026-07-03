# Agnes Video Generator MVP

基于 Agnes Video V2.0 API 的视频生成应用，支持文生视频和图生视频。

## 快速开始

### 1. 配置后端

```bash
cd backend
pip install -r requirements.txt
```

编辑 `backend/.env`，填入你的 Agnes API Key：

```
AGNES_API_KEY=your_actual_api_key
```

启动后端：

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 `http://localhost:5173`。

### 3. 使用

1. 选择模式：文生视频 或 图生视频
2. 输入视频提示词（英文效果更佳）
3. 如选择图生视频，上传一张参考图片
4. 选择宽高比和视频时长
5. 点击"生成视频"
6. 等待生成完成（1-5 分钟），视频自动播放

## 功能

- **文生视频**：根据文本提示词生成视频
- **图生视频**：上传图片并添加运动描述生成动画
- **多种宽高比**：16:9、9:16、1:1、4:3
- **时长选择**：3秒、5秒、10秒、18秒
- **高级参数**：推理步数、随机种子、负面提示词
- **视频流播放**：后端代理流式传输，支持拖动进度条
- **视频下载**：支持下载生成的视频文件

## 技术栈

- 前端：Vue 3 + Vite + TypeScript + Pinia + Axios
- 后端：Python FastAPI + httpx + Pydantic
- API：Agnes Video V2.0 (`agnes-video-v2.0`)

## 项目结构

```
Qoderwork/
├── backend/              # FastAPI 后端
│   ├── .env              # API Key 配置
│   ├── requirements.txt
│   └── app/
│       ├── main.py       # 应用入口
│       ├── config.py     # 环境配置
│       ├── schemas.py    # 数据模型
│       ├── services/
│       │   └── agnes_video.py  # Agnes API 封装
│       └── api/
│           └── video.py  # REST 端点
├── frontend/             # Vue3 前端
│   ├── src/
│   │   ├── api/          # Axios API 层
│   │   ├── stores/       # Pinia 状态管理
│   │   ├── views/        # 页面
│   │   └── components/   # 组件
│   └── ...
└── README.md
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/generate` | 提交生成任务 |
| GET | `/api/generate/{id}` | 查询状态 |
| GET | `/api/generate/{id}/wait` | 长轮询等待完成 |
| GET | `/api/generate/{id}/stream` | 视频流代理（支持 Range） |
| GET | `/api/generate/{id}/download` | 下载视频 |
