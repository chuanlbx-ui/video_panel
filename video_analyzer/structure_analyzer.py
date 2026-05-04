"""
structure_analyzer.py — 模块4b：结构化场景分析

功能:
  结合语音转文字 + 场景切分 + 视觉分析结果，
  输出结构化的场景列表，包含：
  - 每个场景的类型（开场/主体/口播/产品展示/互动/结尾CTA）
  - 场景的文字内容
  - 场景级别视觉特征
  - 整体视频结构分析

不依赖 LLM — 全部基于规则引擎判断。

独立测试:
  python structure_analyzer.py --speech "speech.json" --scenes "scenes.json" --visual "visual.json"

返回格式:
  {
      "total_duration": 45.0,
      "scenes": [
          {"id": "s1", "start": 0, "end": 5, "type": "opening", "text": "大家好..."}
      ],
      "scene_count": 6,
      "estimated_scene_duration": 7.5,
      "has_cta": True
  }
"""

import json
import os
import sys
import re


# ============================================================
# 核心函数
# ============================================================

def analyze_structure(
    speech_segments: list,
    scene_changes: list,
    visuals: dict = None,
) -> dict:
    """
    结合语音 + 场景切分 + 视觉信息，输出结构化场景列表。

    参数:
        speech_segments: 语音段落列表
            [{"start": 0.0, "end": 3.5, "text": "大家好"}, ...]
        scene_changes: 场景切分列表
            [{"start": 0.0, "end": 4.5}, ...]
        visuals: 视觉分析结果（可选）
            {"dominant_colors": [...], "video_type": "...", ...}

    返回:
        dict: 结构化场景信息
    """
    result = {
        "total_duration": 0.0,
        "scenes": [],
        "scene_count": 0,
        "estimated_scene_duration": 0.0,
        "has_cta": False,
        "success": False,
        "error": "",
    }

    try:
        # ---- 校验输入 ----
        if not scene_changes or len(scene_changes) == 0:
            # 如果没有场景切分，用语音段落反推
            if speech_segments and len(speech_segments) > 0:
                scene_changes = _infer_scenes_from_speech(speech_segments)
            else:
                result["error"] = "缺少场景和语音数据"
                return result

        if not speech_segments:
            speech_segments = []

        # ---- 计算总时长 ----
        total_duration = scene_changes[-1]["end"] if scene_changes else 0
        result["total_duration"] = round(total_duration, 2)

        # ---- 将语音段落对齐到场景 ----
        scenes = _align_speech_to_scenes(speech_segments, scene_changes)

        # ---- 分类每个场景类型 ----
        for i, scene in enumerate(scenes):
            scene_text = scene.get("text", "")
            scene_type = classify_scene_type(
                scene_text,
                scene["start"],
                scene["end"],
                total_duration,
                i,
                len(scenes),
                visuals,
            )
            scene["type"] = scene_type
            scene["id"] = f"s{i+1}"

        result["scenes"] = scenes
        result["scene_count"] = len(scenes)

        # ---- 计算平均场景时长 ----
        if len(scenes) > 0:
            avg_duration = total_duration / len(scenes)
            result["estimated_scene_duration"] = round(avg_duration, 2)

        # ---- 检测是否有 CTA ----
        result["has_cta"] = _detect_cta(scenes)

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = f"结构分析异常: {str(e)}"
        return result


def classify_scene_type(
    text: str,
    start: float,
    end: float,
    total_duration: float,
    scene_index: int,
    total_scenes: int,
    visuals: dict = None,
) -> str:
    """
    基于规则分类单个场景的类型。

    场景类型:
      - opening:   开场/引入 (前15%时间 + 问候语)
      - main_content: 主体内容（默认）
      - talking_head: 口播讲解
      - product_showcase: 产品展示
      - interaction: 互动/提问
      - summary:   总结段落
      - cta:       行动号召 (结尾 + 关键词)
      - transition: 转场 (短场景 + 无文本)
      - silent:    静默段落 (无文本)

    参数:
        text: 场景的口播文字
        start: 场景开始时间（秒）
        end: 场景结束时间（秒）
        total_duration: 视频总时长（秒）
        scene_index: 场景索引 (0-based)
        total_scenes: 总场景数
        visuals: 视觉分析结果（可选）

    返回:
        str: 场景类型
    """
    # 标准化文本
    text = (text or "").strip()
    text_lower = text.lower()

    # 计算位置比例
    position_ratio = start / total_duration if total_duration > 0 else 0
    scene_duration = end - start

    # ---- 空文本/无口播 ----
    if not text or len(text) < 2:
        if scene_duration < 2.0:
            return "transition"
        return "silent"

    # ---- CTA / 结尾 ----
    cta_keywords = [
        "关注", "点赞", "订阅", "转发", "评论", "收藏",
        "关注我", "点个赞", "下期", "再见", "拜拜",
        "记得", "关注我们", "关注一下", "关注收藏",
        "follow", "subscribe", "like", "share",
        "点击", "链接", "详情", "了解更多",
        "加我", "私信", "咨询",
    ]
    # 位置在后 20%
    if position_ratio > 0.8:
        if any(kw in text for kw in cta_keywords):
            return "cta"

    # 最后一段场景
    if scene_index == total_scenes - 1 and total_scenes > 2:
        if any(kw in text for kw in cta_keywords):
            return "cta"

    # ---- 开场 ----
    opening_keywords = [
        "大家好", "哈喽", "hello", "hi", "嗨", "欢迎",
        "大家好我是", "大家好，", "hello大家好",
        "今天", "这一期", "这期", "这一集",
    ]
    if position_ratio < 0.15:
        if any(kw in text_lower or kw in text for kw in opening_keywords):
            return "opening"
        # 前 10% + 短场景 → 也可能是开场
        if position_ratio < 0.1 and scene_duration < 10:
            return "opening"

    # ---- 产品展示 ----
    product_keywords = [
        "这款", "这个产品", "推荐", "好物", "好用的",
        "性价比", "测评", "开箱", "使用体验",
        "材质", "质量", "功能", "特点",
        "链接在", "下方", "小黄车", "购物车",
    ]
    if any(kw in text for kw in product_keywords):
        # 检查视觉辅助
        if visuals and visuals.get("video_type") == "product_showcase":
            return "product_showcase"
        return "product_showcase"

    # ---- 互动/提问 ----
    interaction_keywords = [
        "你", "你们", "大家觉得", "是不是", "有没有",
        "告诉我", "评论区", "在评论区", "告诉我",
        "你知道吗", "你了解", "你觉得",
        "?", "？", "投票",
    ]
    if any(kw in text for kw in interaction_keywords) and "?" in text + "？":
        return "interaction"

    # ---- 总结 ----
    summary_keywords = [
        "总结", "总之", "总的来说", "总而言之",
        "以上就是", "以上就是今天", "最后总结",
        "回顾一下", "简单总结", "核心要点",
    ]
    if any(kw in text for kw in summary_keywords):
        return "summary"

    # ---- 口播（默认主体内容） ----
    # 如果是竖屏视频类型，大多数场景都是 talking_head
    if visuals and visuals.get("video_type") in ("talking_head", "interview"):
        if scene_duration > 3.0 and len(text) > 10:
            return "talking_head"

    # ---- 转场 ----
    if scene_duration < 3.0 and len(text) < 15:
        return "transition"

    # ---- 默认 ----
    if position_ratio < 0.2:
        return "opening"
    elif position_ratio > 0.85:
        return "cta"
    else:
        return "main_content"


def _infer_scenes_from_speech(speech_segments: list) -> list:
    """
    当没有场景切分数据时，使用语音段落反推场景。

    策略: 如果两段语音间有 >1.5 秒的间隔，认为是一个场景切换。

    参数:
        speech_segments: 语音段落列表

    返回:
        list: 场景列表 [{"start": ..., "end": ...}, ...]
    """
    if not speech_segments:
        return [{"start": 0.0, "end": 10.0}]

    scenes = []
    prev_end = 0.0

    for seg in speech_segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        # 如果当前段开始距离上一段结束 > 1.5秒，新建场景
        if seg_start - prev_end > 1.5 and scenes:
            scenes.append({"start": prev_end, "end": seg_start})

        if not scenes:
            scenes.append({"start": seg_start, "end": seg_end})
        else:
            scenes[-1]["end"] = max(scenes[-1]["end"], seg_end)

        prev_end = seg_end

    return scenes


def _align_speech_to_scenes(
    speech_segments: list,
    scene_changes: list,
) -> list:
    """
    将语音文本对齐到场景切分中。

    每个场景会包含落在其时间范围内的所有语音文本。

    参数:
        speech_segments: 语音段落
        scene_changes: 场景切分

    返回:
        list: 添加了文本的场景列表
    """
    scenes = []
    for scene in scene_changes:
        scene_start = scene["start"]
        scene_end = scene["end"]

        # 收集落在该时间范围内的语音文本
        text_parts = []
        for seg in speech_segments:
            seg_start = seg.get("start", 0)
            seg_end = seg.get("end", 0)
            seg_text = seg.get("text", "")

            # 判断是否重叠
            if seg_start < scene_end and seg_end > scene_start:
                text_parts.append(seg_text)

        scenes.append({
            "start": scene_start,
            "end": scene_end,
            "text": "".join(text_parts).strip(),
        })

    return scenes


def _detect_cta(scenes: list) -> bool:
    """
    检测视频中是否有 CTA（行动号召）段落。

    参数:
        scenes: 已分类的场景列表

    返回:
        bool: 是否包含 CTA
    """
    cta_keywords = [
        "关注", "点赞", "订阅", "转发", "评论", "收藏",
        "关注我", "点个赞", "下期", "再见",
        "follow", "subscribe", "like", "share",
        "点击", "链接", "详情", "了解更多",
    ]

    for scene in scenes:
        text = scene.get("text", "")
        for kw in cta_keywords:
            if kw in text:
                return True

        # 或者场景类型本身就是 cta
        if scene.get("type") == "cta":
            return True

    return False


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="结构化场景分析")
    parser.add_argument("--speech", type=str, required=True, help="语音分析结果 JSON 文件")
    parser.add_argument("--scenes", type=str, required=True, help="场景切分 JSON 文件")
    parser.add_argument("--visual", type=str, default=None, help="视觉分析结果 JSON 文件（可选）")
    args = parser.parse_args()

    print("=" * 60)
    print("structure_analyzer.py — 独立测试")
    print("=" * 60)

    # 加载数据
    def load_json(path):
        if not os.path.exists(path):
            print(f"[错误] 文件不存在: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    speech_result = load_json(args.speech)
    scenes_data = load_json(args.scenes)

    visuals = None
    if args.visual and os.path.exists(args.visual):
        visuals = load_json(args.visual)
        print(f"已加载视觉数据")
    else:
        print(f"未提供视觉数据，仅使用语音+场景分析")

    # 提取语音段落
    speech_segments = speech_result.get("segments", []) if isinstance(speech_result, dict) else speech_result

    print(f"语音段落:  {len(speech_segments)} 段")
    print(f"场景切分:  {len(scenes_data)} 个")

    result = analyze_structure(speech_segments, scenes_data, visuals)

    print(f"\n--- 结果 ---")
    print(f"  成功:     {result['success']}")
    print(f"  总时长:   {result['total_duration']}s")
    print(f"  场景数:   {result['scene_count']}")
    print(f"  均长:     {result['estimated_scene_duration']}s")
    print(f"  有CTA:    {result['has_cta']}")

    if not result["success"]:
        print(f"  错误:     {result['error']}")
        sys.exit(1)

    print(f"\n--- 场景列表 ---")
    for s in result["scenes"]:
        duration = s["end"] - s["start"]
        text_preview = s["text"][:60].replace("\n", " ") if s["text"] else "(无口播)"
        print(f"  {s['id']:4s}  [{s['start']:6.2f}s → {s['end']:6.2f}s] "
              f"{s['type']:20s} {duration:5.1f}s  {text_preview}")

    print("\n✅ 结构分析完成")
