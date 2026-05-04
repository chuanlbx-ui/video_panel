"""
video_analyzer — 视频分析四步工作流

四个独立分析模块：
1. video_downloader.py  — 下载 & 音频提取 & 元信息
2. scene_detector.py    — 场景切分检测
3. speech_analyzer.py   — 语音转文字 (Whisper)
4. visual_analyzer.py   — 关键帧视觉分析
5. structure_analyzer.py— 结构化场景（结合语音+视觉）

每个模块可独立运行，所有函数返回统一字典格式。
不依赖 LLM（LLM 在 template_generator.py 中使用）。
"""

from .video_downloader import (
    download_video,
    extract_metadata,
    extract_audio,
)
from .scene_detector import (
    detect_scenes,
    merge_short_scenes,
    split_long_scenes,
)
from .speech_analyzer import (
    analyze_speech,
    compute_speech_speed,
)
from .visual_analyzer import (
    analyze_visuals,
    extract_dominant_colors,
    classify_video_type,
)
from .structure_analyzer import (
    analyze_structure,
    classify_scene_type,
)

__version__ = "1.0.0"
__all__ = [
    "download_video",
    "extract_metadata",
    "extract_audio",
    "detect_scenes",
    "merge_short_scenes",
    "split_long_scenes",
    "analyze_speech",
    "compute_speech_speed",
    "analyze_visuals",
    "extract_dominant_colors",
    "classify_video_type",
    "analyze_structure",
    "classify_scene_type",
]
