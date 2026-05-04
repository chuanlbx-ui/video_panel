#!/usr/bin/env python3
"""
template_generator.py — 分析结果 → template_config 转换模块

将 video_analyzer 的分析结果转换为可直接用于渲染的模板配置。
支持 LLM 增强转换（当可用时）。

主要函数:
  analysis_to_template(analysis_result: dict, template_name: str) -> dict
"""
import json, logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from llm_client import llm_match_template
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False
    logger.info("[模板生成] LLM 不可用，使用规则引擎转换")


def analysis_to_template(analysis_result: dict, template_name: str = "ai_analyzed_video") -> dict:
    """
    将视频分析结果转换为可渲染的 template_config 字典。

    参数:
        analysis_result: video_analyzer 各模块分析结果的合并字典
        template_name:   生成的模板名称

    返回:
        dict: 符合渲染管线要求的 template_config
    """
    scenes = analysis_result.get("_raw_scenes", [])
    structure = analysis_result.get("scenes", analysis_result.get("structured_scenes", []))
    speech_segments = analysis_result.get("segments", [])

    # 优先使用结构化场景
    source_scenes = structure if structure else scenes[:10]

    template_scenes = []
    for i, scene_info in enumerate(source_scenes):
        scene_id = f"scene_{i:02d}"

        if isinstance(scene_info, dict):
            duration = scene_info.get("duration", 4.0)
            # 提取文案
            text_content = (
                scene_info.get("title")
                or scene_info.get("text")
                or scene_info.get("description")
                or scene_info.get("caption")
                or f"场景 {i+1}"
            )
            # 提取副标题（如果有）
            subtitle_text = scene_info.get("subtitle", scene_info.get("sub_text", ""))
        else:
            duration = 4.0
            text_content = f"场景 {i+1}"
            subtitle_text = ""

        elements = {
            "title": {
                "text": text_content,
                "font_size": 52,
                "color": "#FFFFFF",
                "align": "center"
            }
        }
        if subtitle_text:
            elements["subtitle"] = {
                "text": subtitle_text,
                "font_size": 36,
                "color": "#CCCCCC",
                "align": "center"
            }

        template_scenes.append({
            "id": scene_id,
            "duration": duration,
            "elements": elements
        })

    # 尝试 LLM 增强（如果可用）
    if _LLM_AVAILABLE and speech_segments:
        try:
            enhanced = llm_match_template(analysis_result, template_name)
            if enhanced and isinstance(enhanced, dict) and "scenes" in enhanced:
                template_scenes = enhanced["scenes"]
                logger.info("[模板生成] 已应用 LLM 增强场景")
        except Exception as e:
            logger.warning(f"[模板生成] LLM 增强失败，使用规则引擎: {e}")

    template_config = {
        "template_name": template_name,
        "width": analysis_result.get("width", 1080),
        "height": analysis_result.get("height", 1920),
        "duration": analysis_result.get("duration", 30.0),
        "fps": analysis_result.get("fps", 30),
        "colors": {
            "scheme": "warm_dark",
            "primary": "#E8491D",
            "secondary": "#FFD700",
            "bg_start": "#1a1a2e",
            "bg_end": "#16213e"
        },
        "animation": {
            "style": "standard",
            "transition": "fade"
        },
        "background": {
            "type": "gradient",
            "color_start": "#1a1a2e",
            "color_end": "#16213e"
        },
        "audio": {
            "voiceover": {
                "enabled": True,
                "voice": "zh-CN-YunyangNeural"
            },
            "bgm": {
                "enabled": True,
                "file": "uplifting"
            }
        },
        "subtitles": {
            "enabled": True
        },
        "scenes": template_scenes,
        "settings": {
            "fps": analysis_result.get("fps", 30),
            "output_width": analysis_result.get("width", 1080),
            "output_height": analysis_result.get("height", 1920),
            "quality": "standard",
            "video_bitrate": "10M",
            "pixel_format": "yuv420p",
            "bg_type": "gradient"
        },
        "effects": {
            "transition_style": "fade",
            "particle_density": "medium",
            "glow_enabled": False
        },
        "_source": "ai_analysis",
        "_analysis_job_id": analysis_result.get("_analysis_job_id", "")
    }

    return template_config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 简单测试
    test_result = {
        "duration": 45.2,
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "_raw_scenes": [
            {"duration": 5.0, "title": "开场介绍"},
            {"duration": 8.0, "title": "核心内容"},
        ],
        "segments": [{"text": "大家好", "start": 0.0, "end": 2.0}],
        "scenes": [
            {"duration": 5.0, "title": "开场介绍", "subtitle": "欢迎收看"},
            {"duration": 8.0, "title": "核心内容", "subtitle": "重点解析"},
        ]
    }
    config = analysis_to_template(test_result)
    print(json.dumps(config, ensure_ascii=False, indent=2)[:500])
    print("...")
    print("template_generator.py 测试通过 ✓")
