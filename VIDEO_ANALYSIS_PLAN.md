# 视频链接→模板生成 完整技术实现方案

## 一、整体架构概览

```
用户输入视频URL
       │
       ▼
┌──────────────────────────────────────┐
│  Step 1: 视频分析（video_analyzer）     │
│  ┌────────────┐  ┌─────────────────┐ │
│  │ yt-dlp下载  │  │ FFmpeg 抽帧     │ │
│  │ 提取音频    │  │ +场景检测       │ │
│  └────┬───────┘  └───────┬─────────┘ │
│       │                  │           │
│       ▼                  ▼           │
│  ┌──────────────────────────────────┐│
│  │ Whisper 语音转文字               ││
│  │ OpenCV 视觉分析（转场/字幕/风格）││
│  │ LLM 结构化总结（提取结构/元素）  ││
│  └──────────────────────────────────┘│
└─────────────────┬────────────────────┘
                  │ 分析结果 JSON
                  ▼
┌──────────────────────────────────────┐
│  Step 2: 分析结果→template_config    │
│  template_generator.py              │
│  映射规则引擎                        │
│  - scenes[] 根据视频结构生成          │
│  - colors 从色调提取                  │
│  - effects 从转场检测                 │
│  - audio/voiceover 从口播提取         │
└─────────────────┬────────────────────┘
                  │ template_config.json
                  ▼
┌──────────────────────────────────────┐
│  Step 3: 用户编辑 → 渲染生成          │
│  复用现有 pipeline:                   │
│  build_from_config.py                │
│  → hyperframes CLI (Puppeteer)       │
│  → edge-tts → FFmpeg 合成            │
└──────────────────────────────────────┘
```

---

## 二、Step 1: 视频分析方案

### 2.1 工具链选择

| 功能 | 工具 | 安装方式 |
|------|------|---------|
| 视频下载 | yt-dlp | `pip install yt-dlp` |
| 音频提取 | FFmpeg (已安装) | 系统已有 |
| 语音转文字 | faster-whisper | `pip install faster-whisper` |
| 场景检测/抽帧 | PySceneDetect + OpenCV | `pip install scenedetect opencv-python-headless` |
| 视觉分析 | OpenCV (色调直方图、边缘检测) | 同上 |
| 结构化总结 | LLM (已有 llm_client.py) | 复用现有 |

### 2.2 下载模块 (video_downloader.py)

```python
# 核心流程
def download_video(url: str, output_dir: Path) -> dict:
    """下载视频+提取音频，返回文件路径信息"""
    # 1. yt-dlp 下载最佳质量视频
    #    yt-dlp -f "bestvideo[height<=1080]+bestaudio/best[height<=1080]" 
    #          -o "{output_dir}/source_video.%(ext)s" {url}
    # 2. FFmpeg 提取音频为16kHz WAV（供Whisper使用）
    #    ffmpeg -i source_video.mp4 -ar 16000 -ac 1 audio.wav
    # 3. FFprobe 获取视频元信息（时长、分辨率、fps等）
    #    ffprobe -v quiet -print_format json -show_streams source_video.mp4
    # 返回: {video_path, audio_path, duration, width, height, fps, format}
```

### 2.3 场景检测模块 (scene_detector.py)

```python
def detect_scenes(video_path: str) -> list:
    """
    使用 PySceneDetect 检测镜头切换点
    - ContentDetector: 基于内容变化的场景分割
    - ThresholdDetector: 基于黑场/淡入淡出检测
    返回: [{"start": 0.0, "end": 4.5, "type": "cut"}, ...]
    """
    # 或用 FFmpeg 做场景检测（无需额外安装）
    # ffmpeg -i video.mp4 -filter:v "select='gt(scene,0.4)',showinfo" -f null - 2>&1
```

### 2.4 语音分析模块 (speech_analyzer.py)

```python
def analyze_speech(audio_path: str) -> dict:
    """
    使用 faster-whisper 进行语音转文字
    返回:
    {
        "full_text": "完整的口播文字",
        "segments": [
            {"start": 0.0, "end": 3.5, "text": "大家好，今天我们来..."},
            ...
        ],
        "duration": 45.2,
        "speed": "normal",  # 语速判断
    }
    """
```

### 2.5 视觉分析模块 (visual_analyzer.py)

```python
def analyze_visuals(video_path: str, scene_timestamps: list) -> dict:
    """
    对关键帧进行多维分析
    返回:
    {
        "dominant_colors": ["#1a1a2e", "#16213e"],  # 主色调
        "color_palette": "dark_blue",                # 配色风格标签
        "has_subtitles": True,                       # 是否有内嵌字幕
        "subtitle_region": [0, 1700, 1080, 1920],    # 字幕区域(x,y,w,h)
        "transition_style": "fade",                  # 转场风格
        "transition_speed": "medium",                # 转场速度
        "text_positions": ["center", "bottom"],       # 文字排版位置
        "video_type": "talking_head",                # 视频类型
        "has_logo": True,                            # 是否有水印/logo
        "frame_rate": 30,
        "aspect_ratio": "9:16",                      # 竖屏/横屏
        "average_luminance": 0.35,                   # 平均亮度
    }
    """
    # 关键技术:
    # 1. 色调提取: 用OpenCV k-means聚类主色调
    # 2. 字幕检测: 用边缘检测定位底部文字区域 + OCR
    # 3. 转场检测: 帧间差异分析 + 已检测的场景切换点
    # 4. 视频类型: 人脸检测判断talking_head vs 幻灯片 vs 实拍
    # 5. 文字位置: 水平投影分析
```

### 2.6 结构分析模块 (structure_analyzer.py)

```python
def analyze_structure(speech_segments: list, scene_changes: list, visuals: dict) -> dict:
    """
    结合语音时间轴和视觉场景变化，分析视频结构
    返回:
    {
        "total_duration": 60.0,
        "scenes": [
            {
                "id": "s1",
                "start": 0.0, "end": 5.0,
                "type": "opening",          # 开场/内容/结尾/CTA
                "text": "大家好，欢迎收看...",
                "duration": 5.0,
                "elements": {
                    "main_text": "标题文字",
                    "sub_text": "副标题"
                }
            },
            ...
        ],
        "narration_full": "完整的口播文字",
        "template_style": "talking_head_with_captions",
        "scene_count": 6,
        "has_cta": True,
        "estimated_scene_duration": 5.0  # 平均场景时长
    }
    """
    # 核心逻辑:
    # 1. 场景对齐: 将 speech_segments 按 scene_changes 分组
    # 2. 类型分类: 开场(first 15%) / 结尾(last 15%) / 中间内容
    # 3. CTA检测: 关键词匹配 "关注" "点赞" "订阅" "联系" 等
    # 4. 结构提取: LLM对完整文稿做结构化总结
```

### 2.7 LLM 结构化总结 (复用 llm_client.py)

现有的 `llm_client.py` 已有 `llm_match_template` 和 `llm_optimize_copy`，新增:

```python
def llm_extract_structure(full_text: str, scene_timestamps: list) -> dict:
    """
    使用LLM分析文稿结构，返回结构化场景列表
    Prompt: "分析以下视频文稿的结构，识别出开场白、各个要点、结尾CTA等，
             按时间顺序输出每个场景的主题和关键文案..."
    """
```

---

## 三、Step 2: 分析结果 → template_config.json 映射

### 3.1 映射引擎 (template_generator.py)

这是核心模块，将分析结果映射为标准的 template_config.json 格式。

```python
from typing import Dict, Any
from pathlib import Path

TEMPLATE_SCHEMA = {
    "template_id": str,        # 自动生成
    "template_name": str,      # 根据内容生成
    "version": "1.0",
    "description": str,
    "source": "ai_analyzed",   # 标记为AI分析生成
    "settings": {
        "video_duration": float,   # 分析得出
        "output_width": int,       # 1080（竖屏适配）
        "output_height": int,      # 1920
        "fps": int,                # 从原视频
        "quality": "standard",
        "video_bitrate": "15M",
        "pixel_format": "yuv420p",
        "bg_type": str             # 从分析结果
    },
    "background": {
        "type": "gradient",        # 或 "image", "video_loop"
        "options": [...]           # 推荐背景
    },
    "audio": {
        "bgm": {
            "enabled": True,
            "volume": 0.12,
            "options": [...]       # 根据视频风格推荐BGM类型
        },
        "voiceover": {
            "enabled": True,
            "text": str,           # 从Whisper提取
            "voice": str,          # 根据语速/性别推荐
            "speed": float         # 根据原视频语速
        }
    },
    "colors": {
        "scheme": str,             # 从主色调映射
        "options": [...]           # 推荐配色方案
    },
    "effects": {
        "transition_style": str,   # 从原视频转场分析
        "particle_density": str,
        "glow_enabled": bool
    },
    "animation": {
        "style": str,              # 根据视频节奏推荐
        "options": [...]
    },
    "subtitles": {
        "enabled": bool,           # 原视频有字幕则启用
        "style": "auto_generated"
    },
    "scenes": [...]               # 核心：从分析结构生成
}
```

### 3.2 场景映射规则（核心）

```python
def analysis_to_scenes(analysis: dict) -> list:
    """
    分析结果 → template_config.json 的 scenes[]
    映射策略：
    """
    scenes = []
    current_time = 0.0
    
    # 规则1: 开场场景映射
    # 提取标题风格文案 → title element
    # 开场白 → subtitle/desc element
    
    # 规则2: 内容场景映射
    # 每段 speech_segment (3-8秒) 生成一个场景
    # 核心文字 → large_white style
    # 补充说明 → subtitle style
    
    # 规则3: 结尾/CTA场景映射
    # 关键词检测：关注/订阅/联系 → CTA场景
    # 电话/地址 → phone/info element
    
    # 规则4: 时长映射
    # 每个场景 duration = 原视频对应段落时长
    # 统一化处理：最短3秒，最长8秒
    
    # 规则5: 元素风格映射
    # talking_head → 简化排版，偏下位置
    # 幻灯片/知识分享 → bullet/point 风格
    # 产品展示 → large_white + subtitle
    
    # 规则6: narration 映射
    # 从 speech_segments 中提取对应段落
    # 每个场景的 narration = 该时段的语音文本
    
    return scenes
```

### 3.3 颜色映射规则

| 视频主色调 | 映射到配色方案 | 
|-----------|---------------|
| 深蓝/科技蓝 | tech_blue |
| 暗色调+金色 | dark_gold |
| 简约白/浅色 | minimal_white |
| 暖色/红色 | warm_dark |
| 紫色/赛博 | cyber_purple |
| 绿色/自然 | neon_green |

### 3.4 语音映射规则

| 原视频特征 | TTS推荐 |
|-----------|---------|
| 男声、语速慢、专业 | zh-CN-YunyangNeural |
| 男声、语速快、激情 | zh-CN-YunjianNeural |
| 女声、温暖 | zh-CN-XiaoxiaoNeural |
| 女声、活泼 | zh-CN-XiaoyiNeural |
| 男声、自然沉稳 | zh-CN-YunyeNeural |
| 语速快 (≥4字/秒) | speed=1.1~1.2 |
| 语速慢 (≤2字/秒) | speed=0.9~1.0 |

### 3.5 转场映射规则

| 检测到的转场类型 | 映射为 effects.transition_style |
|-----------------|-------------------------------|
| 淡入淡出(黑场帧) | fade |
| 滑动(水平偏移) | slide |
| 缩放(尺寸变化) | zoom |
| 硬切(无明显过渡) | fade (默认) |

---

## 四、Step 3: 渲染生成适配方案

### 4.1 复用现有管线的优势

现有管线非常完善，可以直接复用：

```
build_from_config.py (模板级)
  ├── build_html(config) → index.html  ← 复用各模板的HTML生成逻辑
  ├── hyperframes render (Puppeteer)   ← 复用渲染
  ├── edge-tts (TTS)                   ← 复用配音
  └── FFmpeg (音视频合成)              ← 复用合成
```

### 4.2 适配要点

**模板目录结构**：每个AI分析生成的模板有自己的独立目录

```
/home/agentuser/hyperframes_projects/
  └── ai_analyzed_{uuid}/
      ├── template_config.json    # Step 2 生成
      ├── build_from_config.py    # 复制最匹配的现有模板
      └── assets/                 # 从原视频提取的素材(可选)
```

**build_from_config.py 选择策略**：根据分析结果的 video_type 选择最匹配的已有模板的 build 脚本

| 分析结果.video_type | 推荐复用的模板 |
|-------------------|---------------|
| talking_head | personal_ip |
| product_showcase | product_seed |
| knowledge_card | xiaohongshu_style |
| news_update | ai_daily_video |
| event_promo | event_invite |
| food_review | food_promo |
| store_intro | store_promo |

### 4.3 前端适配

在 `index_v4_phone.html` 中新增"AI智能分析"页面：

1. 输入框：粘贴视频链接
2. "开始分析"按钮 → 调用 `/api/analyze-video` 接口
3. 分析进度轮询（类似现有 job 系统）
4. 分析完成后展示模板预览 + 编辑文案
5. 用户确认后生成

---

## 五、后端 API 设计

新建 `api_video_analysis.py`，注册以下路由：

### 5.1 路由清单

```python
# POST /api/analyze-video
# 请求: {"url": "https://..."}
# 响应: {"job_id": "analysis_xxx", "status": "analyzing"}
# 说明: 启动异步分析任务

# GET /api/analyze-status/<job_id>
# 响应: {"status": "analyzing/completed/failed", 
#        "progress": 50,
#        "result": {...}  # 分析结果(completed时)
#       }

# POST /api/analyze-to-template
# 请求: {"analysis_job_id": "analysis_xxx", 
#        "edits": {场景文案编辑}}
# 响应: {"template_id": "ai_analyzed_xxx",
#        "template_config": {...},
#        "status": "ready"
#       }

# POST /api/analyze-generate
# 请求: {"template_id": "ai_analyzed_xxx",
#        "user_params": {...}}
# 响应: {"job_id": "job_xxx", "status": "rendering"}
# 说明: 使用分析生成的模板渲染视频（复用现有render_video）

# GET /api/analyze-templates
# 响应: {"templates": [AI分析生成的模板列表]}
```

### 5.2 异步分析流程

```python
def _analysis_worker(job_id: str, url: str):
    """后台分析线程"""
    try:
        # 1. 下载视频
        JOBS[job_id]["progress"] = 10
        download_info = download_video(url, work_dir)
        
        # 2. 场景检测
        JOBS[job_id]["progress"] = 25
        scenes = detect_scenes(download_info["video_path"])
        
        # 3. 语音分析
        JOBS[job_id]["progress"] = 40
        speech = analyze_speech(download_info["audio_path"])
        
        # 4. 视觉分析
        JOBS[job_id]["progress"] = 60
        visuals = analyze_visuals(download_info["video_path"], scenes)
        
        # 5. 结构分析
        JOBS[job_id]["progress"] = 75
        structure = analyze_structure(speech["segments"], scenes, visuals)
        
        # 6. LLM结构化总结
        JOBS[job_id]["progress"] = 85
        llm_result = llm_extract_structure(structure["narration_full"], scenes)
        
        # 7. 组合最终结果
        JOBS[job_id]["progress"] = 95
        analysis_result = {**download_info, **speech, **visuals, 
                           **structure, "llm_analysis": llm_result}
        
        JOBS[job_id]["result"] = analysis_result
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["progress"] = 100
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
```

---

## 六、文件清单（新建模块）

```
hyperframes_projects/
├── api_video_analysis.py          # 分析相关API路由
├── video_analyzer/
│   ├── __init__.py
│   ├── video_downloader.py       # yt-dlp下载+FFmpeg提取
│   ├── scene_detector.py         # PySceneDetect/FFmpeg场景检测
│   ├── speech_analyzer.py        # faster-whisper语音转文字
│   ├── visual_analyzer.py        # OpenCV视觉分析
│   ├── structure_analyzer.py     # 结构分析引擎
│   └── llm_analyzer.py           # LLM结构化总结
├── template_generator.py         # 核心：分析结果→template_config映射
└── templates/
    └── index_v4_phone.html       # 前端适配（新增AI分析页面）
```

---

## 七、技术可行性评估

### 7.1 ✅ 完全可行的部分

| 模块 | 可行性 | 依据 |
|------|--------|------|
| yt-dlp下载 | ✅ 成熟 | pip install即可，支持所有主流平台 |
| FFmpeg抽帧/场景检测 | ✅ 已就绪 | FFmpeg已在系统上，filter scene检测成熟 |
| faster-whisper | ✅ 可行 | x86_64上运行良好，中文识别准确率高 |
| OpenCV视觉分析 | ✅ 成熟 | 主色调聚类、边缘检测、人脸检测均为成熟API |
| template_config映射 | ✅ 完全可控 | 所有映射规则可硬编码+LLM辅助 |
| 渲染复用 | ✅ 零改动 | 直接调用现有render_video() |

### 7.2 ⚠️ 需要注意的点

| 项目 | 风险等级 | 说明 |
|------|---------|------|
| yt-dlp法律合规 | ⚠️ 低 | 仅用于分析用户提供的公开链接，不存储 |
| faster-whisper模型大小 | ⚠️ 中 | 首次下载~2GB模型文件（base模型~150MB可选） |
| 分析耗时 | ⚠️ 中 | 60秒视频分析约需2-5分钟（下载+转写+分析）|
| 字幕OCR准确性 | ⚠️ 中 | 需配合LLM纠错 |
| 模板质量 | ⚠️ 低 | 生成的是"参考模板"，允许用户手动调整 |

### 7.3 ❌ 不做/简化的部分

| 功能 | 策略 | 理由 |
|------|------|------|
| 精确的字体/颜色复刻 | 仅提取色调+推荐配色 | 精确复刻成本高，用户的素材不同 |
| BGM提取/分离 | 不做 | 版权风险，用模板自带BGM替代 |
| 原视频素材复用 | 不下载图片素材 | 用免费图库代替 |
| 构建脚本自动生成 | 复用最匹配的现有脚本 | 每个模板的HTML逻辑差异大，手写覆盖不现实 |

---

## 八、开发时间预估

| 阶段 | 任务 | 预估工时 | 说明 |
|------|------|---------|------|
| **Phase 1** | 环境准备 | 0.5天 | pip安装yt-dlp, faster-whisper, opencv, scenedetect |
| | video_downloader | 0.5天 | yt-dlp封装+FFmpeg提取 |
| | scene_detector | 0.3天 | FFmpeg scene filter检测 |
| **Phase 2** | speech_analyzer | 1天 | faster-whisper接入+中文优化 |
| | visual_analyzer | 1天 | OpenCV色调+字幕+转场检测 |
| | structure_analyzer | 0.5天 | 场景对齐+类型分类 |
| **Phase 3** | template_generator | 1.5天 | 核心映射引擎（复杂逻辑） |
| | llm_analyzer | 0.5天 | LLM结构化Prompt设计 |
| **Phase 4** | api_video_analysis | 1天 | 后端路由+异步任务 |
| | 前端适配 | 1天 | 分析页面+进度展示+编辑界面 |
| **Phase 5** | 集成测试+优化 | 1天 | 全流程联调+边界情况处理 |
| | 合计 | **8.3天** | 约2周（含周末buffer） |

### 关键路径
- `speech_analyzer` 和 `visual_analyzer` 可并行开发（共1.5天）
- `template_generator` 是最核心且最复杂的模块（1.5天）
- 前端适配可与后端并行（1天）

---

## 九、风险管理

1. **视频平台限制**：部分平台（如抖音、小红书）视频可能无法直接下载
   - 缓解方案：提示用户手动上传视频作为备选
   
2. **Whisper中文识别**：口音/背景噪音会影响准确率
   - 缓解方案：配合LLM做上下文纠错

3. **模板生成质量**：自动生成的模板可能需要手动调整
   - 缓解方案：模板生成后提供在线编辑界面,用户可自由修改文案和场景

4. **分析耗时过长**：用户等待体验差
   - 缓解方案：实时进度推送+预估剩余时间
