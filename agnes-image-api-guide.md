# Agnes Image API 学习记录

> 基于官方文档（agnes-ai.com/doc/agnes-image-21-flash）+ agnes-prompt-studio 项目实战代码整理
> 整理时间：2026-07-03

---

## 一、模型概述

| 项目 | 说明 |
|------|------|
| 模型名称 | `agnes-image-2.1-flash` |
| API 基础地址 | `https://apihub.agnes-ai.com/v1` |
| 图像生成端点 | `POST /v1/images/generations` |
| 认证方式 | Bearer Token（`Authorization: Bearer sk-xxx`） |
| 协议兼容 | OpenAI 标准协议（可通过 LiteLLM 代理接入 Claude Code 等） |
| 定价 | 标准 $0.003/张，当前免费 |
| 适用场景 | 高信息密度图像、复杂视觉细节、语义对齐 |

---

## 二、核心能力

1. **文生图（Text-to-Image）**：根据自然语言提示词直接生成图像
2. **图生图（Image-to-Image）**：基于参考图进行变换/重绘，保留原图构图的同时修改风格/元素
3. **多图层图像融合**：多张参考图融合生成
4. **专业图表绘制**：原生支持架构图、流程图、时序图等技术图表（不局限于插画）

---

## 三、请求参数

### 3.1 参数总览

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定 `agnes-image-2.1-flash` |
| `prompt` | string | 是 | 文本生成指令 |
| `size` | string | 是 | 输出尺寸，如 `1024x768`、`3840x2160` |
| `image` | string[] | 图生图必填 | 输入图片数组（公开 URL 或 Data URI Base64） |
| `return_base64` | boolean | 否 | 文生图时返回 base64（顶层参数） |
| `extra_body` | object | 否 | 高级工作流参数容器 |
| `extra_body.image` | string[] | 图生图必填 | 与顶层 `image` 二选一，官方推荐放此处 |
| `extra_body.response_format` | string | 否 | `"url"` 或 `"b64_json"` |

### 3.2 关键参数说明

**`image` 字段的位置——关键坑点（已验证）**：

`image` 参数**必须放在 `extra_body.image` 中**，不能放在请求体顶层！LiteLLM 代理层会静默丢弃顶层的非标准参数（`image` 不是 OpenAI 标准参数），导致 API 回退到文生图模式。

诊断方法：检查 API 返回的图片 URL 路径——`/t2i/` 表示文生图回退，`/i2i/` 表示图生图成功。

```python
# ✅ 正确：extra_body.image（唯一能工作的方式）
body = {
    "model": "agnes-image-2.1-flash",
    "prompt": "...",
    "size": "1024x768",
    "extra_body": {
        "image": ["data:image/png;base64,..."],
        "response_format": "url",
    }
}

# ❌ 错误：顶层 image（会被 LiteLLM 代理静默丢弃，回退文生图）
body = {
    "model": "agnes-image-2.1-flash",
    "prompt": "...",
    "size": "1024x768",
    "image": ["data:image/png;base64,..."]  # 顶层，不工作！
}
```

> **重要更正**：此前文档记录"httpx 直调时 extra_body 无效"是**错误的**。
> 2026-07-03 诊断脚本验证：`extra_body.image` → URL 含 `/i2i/`（图生图成功），
> 顶层 `image` → URL 含 `/t2i/`（静默回退文生图）。
> `extra_body` 是唯一能让 img2img 工作的参数通道。

**`response_format` 位置**：

`response_format` 必须放在 `extra_body` 内（与 `image` 一起）。放在顶层会报错。img2img 时在 `extra_body` 中设 `"response_format": "url"` 即可。

**`image` 是数组不是字符串**：

API 要求 `image` 为 `string[]` 数组类型，即使只传一张图也要用数组包裹：`["data:image/png;base64,..."]`。

### 3.3 不支持的参数

以下参数 Agnes Image 2.1 Flash **不支持**：

| 参数 | 原因 | 替代方案 |
|------|------|----------|
| `negative_prompt` | API 不支持 | 将负面概念嵌入主 prompt：`"avoid blur, avoid noise"` |
| `n` | 不支持批量生成 | 循环调用，每次 1 张 |
| `strength` | 不支持图生图强度控制 | 通过 prompt 描述控制修改程度 |
| `tags: ["img2img"]` | 不需要 | 图生图直接传 `image` 即可 |
| 顶层 `response_format` | 会报错 | 放 `extra_body.response_format` 或不传（默认 URL） |

---

## 四、响应格式

### 4.1 响应结构

```json
{
  "created": 1780000000,
  "data": [
    {
      "url": "https://storage.googleapis.com/agnes-aigc/xxx.png",
      "b64_json": null,
      "revised_prompt": null
    }
  ]
}
```

### 4.2 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `created` | integer | 请求时间戳 |
| `data` | array | 生成结果数组（通常 1 个元素） |
| `data[].url` | string/null | 图片 URL（URL 模式时有值） |
| `data[].b64_json` | string/null | Base64 图片数据（base64 模式时有值） |
| `data[].revised_prompt` | string/null | API 修订后的提示词 |

### 4.3 获取图片的两种方式

**URL 模式（默认）**：响应中的 `data[0].url` 是 Google Cloud Storage 链接，需要额外下载。

**Base64 模式**：
- 文生图：请求中设 `return_base64: true`，响应中 `data[0].b64_json` 为 base64 数据
- 图生图：请求中设 `extra_body.response_format: "b64_json"`（httpx 直调时不支持，只能用 URL 模式）

---

## 五、尺寸选项

### 5.1 标准分辨率

官方推荐 `1024x1024`（正方形）。也支持自定义尺寸如 `1024x768`。

### 5.2 4K 分辨率

项目实战中使用的 4K 尺寸：

| 尺寸 | 比例 | 用途 |
|------|------|------|
| `3840x2160` | 16:9 | 横版（视频素材、宽屏展示） |
| `2160x3840` | 9:16 | 竖版（短视频、手机全屏） |
| `4096x4096` | 1:1 | 正方形（高精度产品图） |

### 5.3 4K 限流

4K 分辨率有严格的速率限制：**每 60 秒仅允许 1 次请求**。触发限流返回 429 状态码。

实战策略：
- 主动冷却：每次请求前检查距上次请求是否满 65 秒（5 秒缓冲）
- 429 重试：解析错误消息中的等待时间，休眠后重试（最多 3 次）
- 前端超时设 600 秒（10 分钟），覆盖最坏情况

---

## 六、认证

### 6.1 API Key

- 从 `https://platform.agnes-ai.com/` 控制台获取
- 格式以 `sk-` 开头
- 图像和视频 API 共用同一个 Key
- 通过环境变量 `AGNES_API_KEY` 配置

### 6.2 请求头

```python
headers = {
    "Authorization": f"Bearer {AGNES_API_KEY}",
    "Content-Type": "application/json"
}
```

### 6.3 代理绕过（Windows 重要坑）

Windows 系统代理会导致 httpx 请求**静默失败**（不报错也不返回）。必须创建绕代理的 httpx 客户端：

```python
def _no_proxy_client() -> httpx.AsyncClient:
    transport = httpx.AsyncHTTPTransport(proxy=None)
    return httpx.AsyncClient(transport=transport)
```

所有调 `apihub.agnes-ai.com` 的请求都必须用此客户端。

### 6.4 下载图片不需要认证头

API 返回的图片 URL 在 Google Cloud Storage（`storage.googleapis.com/agnes-aigc/`），**不需要也不应该带 Authorization 头**，否则 GCS 返回 401。只有调 API 创建/查询接口才需要 Bearer 认证。

---

## 七、代码示例

### 7.1 文生图（URL 输出）

```python
import httpx

async def text2img(prompt: str, api_key: str) -> str:
    """文生图，返回图片 URL"""
    transport = httpx.AsyncHTTPTransport(proxy=None)
    async with httpx.AsyncClient(transport=transport, timeout=120) as client:
        resp = await client.post(
            "https://apihub.agnes-ai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "agnes-image-2.1-flash",
                "prompt": prompt,
                "size": "1024x1024",
            },
        )
    data = resp.json()
    return data["data"][0]["url"]  # 图片 URL
```

### 7.2 文生图（Base64 输出）

```python
body = {
    "model": "agnes-image-2.1-flash",
    "prompt": "A luminous floating city above a misty canyon at sunrise",
    "size": "1024x768",
    "return_base64": True,  # 顶层参数，返回 base64
}
# 响应中 data[0]["b64_json"] 为 base64 图片数据
```

### 7.3 图生图（httpx 直调，已验证正确用法）

```python
import httpx
import base64

async def img2img(image_path: str, prompt: str, api_key: str) -> str:
    """图生图，返回图片 URL"""
    # 读取图片并转为 data URI
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    data_uri = f"data:image/png;base64,{img_b64}"

    transport = httpx.AsyncHTTPTransport(proxy=None)
    async with httpx.AsyncClient(transport=transport, timeout=240) as client:
        resp = await client.post(
            "https://apihub.agnes-ai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "agnes-image-2.1-flash",
                "prompt": prompt,
                "size": "3840x2160",
                "extra_body": {  # 必须放在 extra_body 中！
                    "image": [data_uri],
                    "response_format": "url",
                },
            },
        )
    data = resp.json()
    return data["data"][0]["url"]
```

### 7.4 图生图（curl，官方文档用法）

```bash
curl https://apihub.agnes-ai.com/v1/images/generations \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform the scene into a rain-soaked cyberpunk night",
    "size": "1024x768",
    "extra_body": {
      "image": ["data:image/png;base64,BASE64_HERE"],
      "response_format": "url"
    }
  }'
```

### 7.5 下载并保存图片

```python
async def download_and_save(image_url: str, save_path: str):
    """下载 API 返回的图片 URL 并保存到磁盘"""
    transport = httpx.AsyncHTTPTransport(proxy=None)
    async with httpx.AsyncClient(transport=transport, timeout=60) as client:
        # 注意：不带 Authorization 头！GCS 不需要认证
        resp = await client.get(image_url)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)
```

---

## 八、PNG 转换（关键坑点）

### 8.1 问题

Agnes API 对图片 MIME 类型非常严格。如果传入的图片标记为 PNG 但实际是 WebP/JPEG，API 会**静默忽略图片**并回退到文生图模式——不报错，但生成的图片与输入完全不同（画面漂移）。

### 8.2 解决方案

用 Pillow 将所有输入图片统一转为 PNG 格式：

```python
from PIL import Image
import io
import base64

def ensure_png_data_uri(image_data: str) -> str:
    """将任意格式的图片转为合法的 PNG data URI"""
    # 1. 解析原始数据和 MIME 类型
    if image_data.startswith("data:"):
        idx = image_data.find(";base64,")
        if idx != -1:
            header = image_data[:idx]
            mime = header.split(":")[1] if ":" in header else "image/png"
            raw_b64 = image_data[idx + 8:]
        else:
            raw_b64 = image_data
            mime = "image/png"
    else:
        raw_b64 = image_data
        mime = "image/png"

    # 已经是 PNG 则直接返回
    if mime == "image/png":
        return f"data:image/png;base64,{raw_b64}"

    # 2. 解码 base64 → 原始字节
    img_bytes = base64.b64decode(raw_b64)

    # 3. Pillow 转为 PNG
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode in ("RGBA", "LA"):
        pass  # 保留透明通道
    elif img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode()

    return f"data:image/png;base64,{png_b64}"
```

### 8.3 为什么前端要传完整 data URI

前端应发送完整的 `data:image/webp;base64,...`（带前缀），而不是裸 base64。这样后端能检测到原始 MIME 类型（如 webp），执行正确的 PNG 转换。如果只发裸 base64，后端无法判断原始格式。

---

## 九、速率限制与重试策略

### 9.1 4K 限流

| 限制项 | 值 |
|--------|-----|
| 4K 分辨率 | 每 60 秒 1 次请求 |
| 触发限流状态码 | 429 |
| 限流错误消息格式 | `"X requests per Y minute(s)"` |

### 9.2 实战重试逻辑

```python
import time
import asyncio
import re

_last_request_time = 0.0
_RATE_LIMIT_COOLDOWN = 65.0  # 60s 限制 + 5s 缓冲
_MAX_RETRIES = 3

async def call_with_rate_limit(body, headers):
    global _last_request_time

    for attempt in range(_MAX_RETRIES + 1):
        # 主动冷却：距上次请求不足 65 秒则等待
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < _RATE_LIMIT_COOLDOWN and _last_request_time > 0:
            wait = _RATE_LIMIT_COOLDOWN - elapsed
            await asyncio.sleep(wait)

        # 发送请求
        async with _no_proxy_client(timeout=240) as client:
            resp = await client.post(CREATE_URL, headers=headers, json=body)

        _last_request_time = time.time()

        # 429 限流处理
        if resp.status_code == 429:
            if attempt < _MAX_RETRIES:
                error_body = resp.json()
                msg = error_body.get("message", "")
                # 解析 "X minute" 得到等待时间
                wait_match = re.search(r"(\d+)\s*minute", msg)
                retry_wait = int(wait_match.group(1)) * 60 + 5 if wait_match else 65
                await asyncio.sleep(retry_wait)
                _last_request_time = 0  # 重置避免双重等待
                continue
            else:
                raise Exception("4K 图像生成触发限流")

        return resp

    raise Exception("重试次数耗尽")
```

### 9.3 网络错误重试

| 错误类型 | 重试次数 | 退避策略 |
|----------|----------|----------|
| `httpx.ConnectError` | 3 次 | 10s, 20s, 30s |
| `httpx.ReadTimeout` | 3 次 | 10s, 20s, 30s |
| `httpx.HTTPError` | 3 次 | 10s, 20s, 30s |

---

## 十、图片存储策略

### 10.1 不要在前端传 base64

一张 4K PNG 图片的 base64 编码可达 20-40MB。如果直接作为 JSON 返回前端，会导致浏览器 JS 线程冻结。

### 10.2 后端下载+磁盘存储

推荐流程：

```
API 返回图片 URL
    ↓
后端下载图片（60s 超时，不带认证头）
    ↓
保存到 uploads/enhanced-{uuid}.png
    ↓
返回 URL 路径 "/uploads/enhanced-xxx.png" 给前端
    ↓
前端通过 <img src="http://localhost:8000/uploads/xxx.png"> 展示
```

### 10.3 静态文件服务

FastAPI 挂载静态文件目录：

```python
from fastapi.staticfiles import StaticFiles
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
```

---

## 十一、提示词工程

### 11.1 文生图 prompt 结构

```
[主体] + [场景/环境] + [风格] + [光照] + [构图] + [品质要求]
```

示例：`A luminous floating city above a misty canyon at sunrise, cinematic realism, volumetric lighting, wide-angle composition, ultra-detailed 8K`

### 11.2 图生图 prompt 结构

```
[修改指令] + [新风格/场景] + [添加/移除的元素] + [保留的元素]
```

示例：`Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition`

### 11.3 负面提示词处理

API 不支持 `negative_prompt` 参数。替代方案——在主 prompt 中用 `avoid` 句式：

```
Enhance this image to 4K quality, preserve the subject's appearance, 
avoid color changes, avoid blur, avoid noise, avoid oversaturation
```

### 11.4 图像增强默认 prompt

当用户未提供 prompt 时的 fallback：

```
img2img enhancement: upscale and sharpen this exact image to 4K resolution. 
Keep the same subject, composition, colors, and layout — do NOT generate new content. 
Improve detail clarity, texture sharpness, and edge definition only.
```

---

## 十二、内容安全过滤

API 有内容安全过滤，以下内容会被拒绝（返回 "Unable to generate this content"）：

- 版权角色（如 Superman、Mickey Mouse 等）
- 直白暴力描写（agony、snapped back、gore 等）
- 敏感词汇

**应对策略**：
- 用通用描述替代版权角色名（"a caped superhero in red and blue"）
- 用电影动作语言替代暴力描写
- 先用最短 prompt 测试能否过审，再逐步加细节

---

## 十三、错误处理

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 401 Unauthorized | API Key 错误/过期 | 检查 Key 格式（sk- 开头）、无多余空格 |
| 404 Not Found | Base URL 错误 | 确保含 `hub` 和 `/v1` |
| model not found | 模型名错误 | 全小写 `agnes-image-2.1-flash` |
| 429 Too Many Requests | 4K 限流 | 等待 65 秒后重试 |
| 生成空白/失败 | 内容安全过滤 | 简化 prompt，避免敏感词 |
| 画面漂移 | MIME 类型不匹配 | 用 Pillow 统一转 PNG |
| 画面漂移 | image 放在顶层 body 被 LiteLLM 丢弃 | 放 `extra_body.image`，检查 URL 含 `/i2i/` |
| 请求无响应 | 系统代理干扰 | 用 `AsyncHTTPTransport(proxy=None)` 绕代理 |
| 图片下载 401 | 带了不该带的认证头 | 下载 GCS 图片时不带 Authorization |

---

## 十四、与 Agnes Video API 对比

| 项目 | Image API | Video API |
|------|-----------|-----------|
| 模型 | `agnes-image-2.1-flash` | `agnes-video-v2.0` |
| 端点 | `POST /v1/images/generations` | `POST /v1/videos` |
| 查询 | 不需要（同步返回） | `GET /agnesapi?video_id=xxx` |
| 模式 | 同步 | 异步（创建→轮询→获取结果） |
| 图片输入 | `image: [data_uri]`（顶层） | `image: "base64"`（顶层字符串） |
| 超时建议 | 60-240 秒 | 120 秒创建 + 600 秒轮询 |
| 限流 | 4K: 1 次/60 秒 | 1 个并发任务 |
| 存储位置 | GCS（storage.googleapis.com） | GCS（storage.googleapis.com） |
| 共用 | 同一个 API Key | 同一个 API Key |
| 共用 | 同样需绕系统代理 | 同样需绕系统代理 |
| 共用 | 下载都不带 Authorization | 下载都不带 Authorization |

---

## 十五、完整调用流程

```
用户上传图片 (JPG/PNG/WebP)
    │
    ▼
前端: FileReader.readAsDataURL() → data URI string
    │  (data:image/webp;base64,...)
    │
    ▼
前端: POST /api/image/enhance { image, prompt, size }
    │  (axios, timeout=600000ms / 10min)
    │
    ▼
后端: _ensure_png_data_uri(image)
    │  Pillow 转为合法 PNG data URI
    │
    ▼
后端: 速率限制检查 (65s 冷却)
    │  不足 65s 则等待
    │
    ▼
后端: POST https://apihub.agnes-ai.com/v1/images/generations
    │  Headers: Authorization: Bearer sk-xxx
    │  Body: { model, prompt, size, extra_body: { image: [png_data_uri], response_format: "url" } }
    │  Timeout: 240s
    │
    ├── 429 → 解析等待时间 → sleep → 重试 (max 3)
    ├── 网络错误 → 退避重试 [10s, 20s, 30s] (max 3)
    │
    ▼
后端: 解析响应 data[0].url
    │
    ▼
后端: GET 图片 URL (不带 Authorization, 60s 超时)
    │  下载图片二进制数据
    │
    ▼
后端: 保存到 uploads/enhanced-{uuid}.png
    │  返回 { image: "/uploads/xxx.png", revised_prompt: "..." }
    │
    ▼
前端: <img src="http://localhost:8000/uploads/xxx.png" />
```

---

## 十六、依赖清单

```
httpx>=0.27.0        # HTTP 客户端（绕代理、异步请求）
Pillow>=10.0.0       # 图片格式转换（PNG 统一化）
pydantic>=2.6.0      # 数据模型校验
python-dotenv>=1.0.0 # 环境变量加载
```

> 注意：Pillow 在 agnes-prompt-studio 项目中被使用但未在 requirements.txt 中声明，部署时需手动安装。

---

## 十七、参考链接

- 官方文档中心：`agnes-ai.com/doc/Agnes`
- 图像模型教程：`agnes-ai.com/doc/agnes-image-21-flash`
- API Key 管理：`platform.agnes-ai.com`
- 项目实战代码：`E:\Desktop\agnes_project\agnes-prompt-studio\backend\app\services\image_service.py`
