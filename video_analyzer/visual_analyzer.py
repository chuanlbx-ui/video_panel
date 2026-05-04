"""
visual_analyzer.py — 模块4a：关键帧视觉分析

功能:
  对视频进行视觉特征分析，提取：
  - 主色调 / 调色板
  - 字幕检测（画面中是否有文字区域）
  - 宽高比
  - 视频类型分类 (talking_head / slideshow / product_showcase)
  - 平均亮度

分析策略:
  采样视频中的关键帧（每个场景取中间帧），
  对关键帧进行全局视觉分析。

不依赖 LLM — 全部使用 OpenCV/PIL 做传统视觉分析。

独立测试:
  python visual_analyzer.py --video "/path/to/video.mp4"

返回格式:
  {
      "dominant_colors": ["#1a1a2e", "#16213e"],
      "color_palette": "dark_blue",
      "has_subtitles": False,
      "aspect_ratio": "9:16",
      "video_type": "talking_head",
      "average_luminance": 0.35,
      "success": True
  }
"""

import os
import sys
import math
from collections import Counter


# ============================================================
# 核心函数
# ============================================================

def analyze_visuals(video_path: str, scene_timestamps: list = None) -> dict:
    """
    分析视频的视觉特征。

    参数:
        video_path: 视频文件路径
        scene_timestamps: 场景时间戳列表 [{"start": 0, "end": 5}, ...]
                          如果为 None，则在视频中均匀采样 10 帧

    返回:
        dict: 包含主色调、调色板、字幕检测等视觉信息的字典
    """
    result = {
        "dominant_colors": [],
        "color_palette": "unknown",
        "has_subtitles": False,
        "aspect_ratio": "16:9",
        "video_type": "unknown",
        "average_luminance": 0.0,
        "success": False,
        "error": "",
    }

    if not os.path.exists(video_path):
        result["error"] = f"视频文件不存在: {video_path}"
        return result

    try:
        # ---- 获取元信息 ----
        meta = _get_video_meta(video_path)
        if not meta:
            result["error"] = "无法读取视频元信息"
            return result

        width = meta.get("width", 0)
        height = meta.get("height", 0)
        duration = meta.get("duration", 0.0)

        if width <= 0 or height <= 0:
            result["error"] = "无效的视频分辨率"
            return result

        # ---- 计算宽高比 ----
        result["aspect_ratio"] = _compute_aspect_ratio(width, height)

        # ---- 提取关键帧 ----
        frames = _extract_key_frames(video_path, scene_timestamps, duration)

        if not frames:
            result["error"] = "无法提取关键帧"
            return result

        # ---- 分析各帧特征 ----
        all_colors = []
        luminance_values = []
        subtitle_flags = []

        for frame in frames:
            frame_data = _analyze_single_frame(frame, width, height)
            all_colors.extend(frame_data["colors"])
            luminance_values.append(frame_data["luminance"])
            subtitle_flags.append(frame_data["has_text"])

        # ---- 汇总结果 ----
        # 主色调: 提取出现最多的 TOP-3 颜色
        if all_colors:
            color_counter = Counter(all_colors)
            result["dominant_colors"] = [c[0] for c in color_counter.most_common(3)]

            # 调色板分类
            result["color_palette"] = _classify_color_palette(result["dominant_colors"])

        # 平均亮度
        if luminance_values:
            result["average_luminance"] = round(
                sum(luminance_values) / len(luminance_values), 4
            )

        # 字幕检测: 超过半数帧有文字区域则判定为有字幕
        if subtitle_flags:
            result["has_subtitles"] = (
                sum(subtitle_flags) / len(subtitle_flags) > 0.5
            )

        # 视频类型分类
        result["video_type"] = classify_video_type(
            result["dominant_colors"],
            result["average_luminance"],
            result["has_subtitles"],
            result["aspect_ratio"],
            len(frames),
        )

        result["success"] = True
        return result

    except ImportError as e:
        result["error"] = f"缺少依赖库: {str(e)}"
        return result
    except Exception as e:
        result["error"] = f"视觉分析异常: {str(e)}"
        return result


def extract_dominant_colors(video_path: str, num_colors: int = 5) -> list:
    """
    提取视频的主色调列表（简化接口）。

    参数:
        video_path: 视频文件路径
        num_colors: 提取颜色数量

    返回:
        list: 十六进制颜色代码列表，如 ["#1a1a2e", "#16213e", ...]
    """
    result = analyze_visuals(video_path)
    if result["success"]:
        return result["dominant_colors"][:num_colors]
    return []


def classify_video_type(
    colors: list,
    luminance: float,
    has_subtitles: bool,
    aspect_ratio: str,
    frame_count: int,
) -> str:
    """
    基于视觉特征分类视频类型。

    分类规则:
      - talking_head: 竖屏 + 高亮度 + 人脸区域明显
      - slideshow: 横屏 + 高亮度 + 频繁切换
      - product_showcase: 中亮度 + 特定色调 + 缓慢移动
      - outdoor_scene: 高亮度 + 绿色/蓝色为主
      - indoor_scene: 低亮度 + 暖色调
      - interview: 竖屏 + 中性背景 + 有字幕
      - unknown: 无法判断

    参数:
        colors: 主色调列表
        luminance: 平均亮度 (0~1)
        has_subtitles: 是否有字幕
        aspect_ratio: 宽高比字符串
        frame_count: 采样的帧数

    返回:
        str: 视频类型
    """
    is_vertical = aspect_ratio in ("9:16", "3:4", "1:1")
    is_horizontal = aspect_ratio in ("16:9", "4:3", "21:9")

    # 检测暖色/冷色
    warm_colors = ["#ff", "#fc", "#f", "#e", "#d"]
    cold_colors = ["#0", "#1", "#2", "#3"]

    has_warm = any(
        any(c.lower().startswith(w) for w in warm_colors) for c in colors
    )
    has_cold = any(
        any(c.lower().startswith(w) for w in cold_colors) for c in colors
    )

    # 分类逻辑
    if is_vertical:
        if luminance > 0.5 and has_warm and not has_cold:
            return "talking_head"
        elif luminance > 0.4 and has_subtitles:
            return "interview"
        elif luminance < 0.3 and has_cold:
            return "indoor_scene"
        else:
            return "talking_head"  # 竖屏多数是口播
    elif is_horizontal:
        if luminance > 0.6 and frame_count >= 5:
            return "slideshow"
        elif luminance > 0.4 and has_cold:
            return "outdoor_scene"
        elif luminance < 0.4 and has_warm:
            return "product_showcase"
        else:
            return "slideshow"
    else:
        return "unknown"


# ============================================================
# 内部辅助函数
# ============================================================

def _get_video_meta(video_path: str) -> dict:
    """
    使用 FFprobe 获取视频元信息。

    参数:
        video_path: 视频文件路径

    返回:
        dict: {width, height, duration, fps} 或 None
    """
    import json
    import subprocess

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            video_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            return None

        data = json.loads(proc.stdout)

        # 找视频流
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            return None

        duration_str = data.get("format", {}).get("duration", "0")
        try:
            duration = float(duration_str)
        except (ValueError, TypeError):
            duration = 0.0

        return {
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "duration": duration,
        }
    except Exception:
        return None


def _compute_aspect_ratio(width: int, height: int) -> str:
    """
    计算宽高比并返回常见字符串格式。

    参数:
        width: 宽度（像素）
        height: 高度（像素）

    返回:
        str: 如 "16:9", "9:16", "4:3", "1:1"
    """
    if width <= 0 or height <= 0:
        return "16:9"

    # 计算最大公约数
    def gcd(a, b):
        return a if b == 0 else gcd(b, a % b)

    g = gcd(width, height)
    w_ratio = width // g
    h_ratio = height // g

    # 常见宽高比匹配
    common_ratios = {
        (16, 9): "16:9",
        (9, 16): "9:16",
        (4, 3): "4:3",
        (3, 4): "3:4",
        (1, 1): "1:1",
        (21, 9): "21:9",
        (9, 21): "9:21",
    }

    # 尝试精确匹配
    for (rw, rh), label in common_ratios.items():
        if w_ratio == rw and h_ratio == rh:
            return label

    # 近似匹配（允许 ±5% 误差）
    ratio_val = width / height
    if abs(ratio_val - 16 / 9) < 0.05:
        return "16:9"
    elif abs(ratio_val - 9 / 16) < 0.05:
        return "9:16"
    elif abs(ratio_val - 4 / 3) < 0.05:
        return "4:3"
    elif abs(ratio_val - 1.0) < 0.05:
        return "1:1"
    elif abs(ratio_val - 21 / 9) < 0.05:
        return "21:9"

    return f"{w_ratio}:{h_ratio}"


def _extract_key_frames(
    video_path: str,
    scene_timestamps: list,
    duration: float,
) -> list:
    """
    从视频中提取关键帧（每个场景取中间帧，或均匀采样10帧）。

    参数:
        video_path: 视频路径
        scene_timestamps: 场景时间戳列表
        duration: 视频总时长

    返回:
        list: 关键帧列表，每个元素是 (frame_data, timestamp)
    """
    try:
        import cv2
    except ImportError:
        print("[visual_analyzer] OpenCV 不可用")
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    frames = []

    # 确定要采样的时间点
    timestamps = []
    if scene_timestamps and len(scene_timestamps) > 0:
        # 每个场景取中间帧
        for scene in scene_timestamps:
            mid_time = (scene["start"] + scene["end"]) / 2
            timestamps.append(mid_time)
    else:
        # 均匀采样 10 帧
        if duration > 0:
            step = duration / 10
            for i in range(10):
                timestamps.append(step * (i + 0.5))

    # 提取帧
    for ts in timestamps:
        frame_idx = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append((frame, ts))

    cap.release()
    return frames


def _analyze_single_frame(frame, width: int, height: int) -> dict:
    """
    分析单帧图像。

    参数:
        frame: OpenCV 图像 (numpy array, BGR格式)
        width: 原始宽度
        height: 原始高度

    返回:
        dict: {colors: [...], luminance: float, has_text: bool}
    """
    try:
        from PIL import Image
    except ImportError:
        return {"colors": [], "luminance": 0.0, "has_text": False}

    # 转换为 RGB PIL Image
    import cv2
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_frame)

    # ---- 提取主色调 ----
    colors = _extract_colors_from_pil(pil_img)

    # ---- 计算平均亮度 ----
    luminance = _compute_luminance(pil_img)

    # ---- 检测文字区域 ----
    has_text = _detect_text_region(frame, width, height)

    return {"colors": colors, "luminance": luminance, "has_text": has_text}


def _extract_colors_from_pil(pil_img) -> list:
    """
    从 PIL Image 中提取主色调。

    策略: 缩小到 64x64，取出现最多的颜色（量化后）。

    参数:
        pil_img: PIL Image 对象

    返回:
        list: 十六进制颜色代码列表
    """
    # 缩小以减少计算量
    small = pil_img.resize((64, 64))

    # 颜色量化: 降低颜色深度到 4bit (16色/通道)
    # 将 R,G,B 各压缩到 4bit，组合成 12bit 颜色
    quantized = []
    for y in range(small.height):
        for x in range(small.width):
            r, g, b = small.getpixel((x, y))[:3]
            # 量化到 4bit (0-15)
            r_q = (r // 16) * 16 + 8
            g_q = (g // 16) * 16 + 8
            b_q = (b // 16) * 16 + 8
            hex_color = f"#{r_q:02x}{g_q:02x}{b_q:02x}"
            quantized.append(hex_color)

    # 统计出现频率
    counter = Counter(quantized)
    return [c[0] for c in counter.most_common(5)]


def _compute_luminance(pil_img) -> float:
    """
    计算图像的平均亮度 (0~1)。

    参数:
        pil_img: PIL Image 对象

    返回:
        float: 亮度值 (0=纯黑, 1=纯白)
    """
    # 转换为灰度图
    gray = pil_img.convert("L")
    pixels = list(gray.getdata())
    total = sum(pixels)
    count = len(pixels)

    if count == 0:
        return 0.0

    # 归一化到 0~1
    return total / (count * 255.0)


def _detect_text_region(frame, width: int, height: int) -> bool:
    """
    检测画面中是否有文字区域（字幕）。

    策略:
      1. 关注画面底部 1/3 区域（字幕通常位置）
      2. 使用边缘检测 + 形态学操作
      3. 如果底部区域有密集的水平边缘，认为可能有字幕

    参数:
        frame: OpenCV BGR 图像
        width: 图像宽度
        height: 图像高度

    返回:
        bool: 是否有文字区域
    """
    import cv2
    import numpy as np

    try:
        # 取底部 1/3 区域
        bottom_region = frame[int(height * 2 / 3):, :]

        # 转灰度
        gray = cv2.cvtColor(bottom_region, cv2.COLOR_BGR2GRAY)

        # 自适应阈值 + 边缘检测
        edges = cv2.Canny(gray, 50, 150)

        # 形态学膨胀，连接相近的边缘
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        # 计算边缘像素密度
        edge_pixels = np.count_nonzero(dilated)
        total_pixels = dilated.shape[0] * dilated.shape[1]

        if total_pixels == 0:
            return False

        density = edge_pixels / total_pixels

        # 经验阈值: 如果底部有 >5% 的像素是边缘，可能含有文字
        # 同时检查水平方向的纹理特征
        if density > 0.05:
            # 检查水平投影：文字行通常会产生明显的水平条纹
            h_proj = np.sum(dilated, axis=1) / dilated.shape[1]
            # 如果有多个连续的高密度行，判定为有文字
            high_density_rows = np.sum(h_proj > 0.3)
            if high_density_rows >= 3:
                return True

        return False

    except Exception:
        return False


def _classify_color_palette(colors: list) -> str:
    """
    基于主色调分类调色板风格。

    参数:
        colors: 十六进制颜色列表

    返回:
        str: 调色板名称
    """
    if not colors:
        return "unknown"

    # 将颜色转换为 HSV 并分类
    try:
        import colorsys

        hue_buckets = Counter()
        sat_bright = Counter()

        for c in colors:
            c = c.lstrip("#")
            if len(c) != 6:
                continue
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
            h, s, v = colorsys.rgb_to_hsv(r_n, g_n, b_n)

            # 色相分类 (0~360)
            h_deg = h * 360
            if h_deg < 30 or h_deg >= 330:
                hue_buckets["red"] += 1
            elif h_deg < 90:
                hue_buckets["yellow"] += 1
            elif h_deg < 150:
                hue_buckets["green"] += 1
            elif h_deg < 210:
                hue_buckets["cyan"] += 1
            elif h_deg < 270:
                hue_buckets["blue"] += 1
            else:
                hue_buckets["magenta"] += 1

            # 饱和度/亮度分类
            if s < 0.2 and v > 0.8:
                sat_bright["bright"] += 1
            elif s < 0.3:
                sat_bright["muted"] += 1
            elif v < 0.3:
                sat_bright["dark"] += 1
            elif v > 0.8:
                sat_bright["vibrant"] += 1
            else:
                sat_bright["moderate"] += 1

        # 组合
        dominant_hue = hue_buckets.most_common(1)[0][0] if hue_buckets else "unknown"
        dominant_style = sat_bright.most_common(1)[0][0] if sat_bright else "unknown"

        palette_map = {
            ("red", "vibrant"): "vibrant_red",
            ("red", "dark"): "dark_red",
            ("blue", "dark"): "dark_blue",
            ("blue", "vibrant"): "vibrant_blue",
            ("green", "vibrant"): "vibrant_green",
            ("green", "muted"): "muted_green",
            ("yellow", "bright"): "bright_warm",
            ("yellow", "vibrant"): "warm_gold",
            ("magenta", "vibrant"): "vibrant_pink",
            ("magenta", "dark"): "dark_purple",
            ("cyan", "bright"): "cool_cyan",
        }

        key = (dominant_hue, dominant_style)
        if key in palette_map:
            return palette_map[key]

        # 默认映射
        return f"{dominant_style}_{dominant_hue}"

    except Exception:
        return "unknown"


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="视频视觉特征分析")
    parser.add_argument("--video", type=str, required=True, help="视频文件路径")
    parser.add_argument("--scenes", type=str, default=None,
                        help="场景 JSON 文件路径（可选，用于采样关键帧）")
    args = parser.parse_args()

    print("=" * 60)
    print("visual_analyzer.py — 独立测试")
    print("=" * 60)

    if not os.path.exists(args.video):
        print(f"[错误] 文件不存在: {args.video}")
        sys.exit(1)

    # 尝试加载场景时间戳
    scene_timestamps = None
    if args.scenes and os.path.exists(args.scenes):
        import json
        with open(args.scenes, "r", encoding="utf-8") as f:
            scene_timestamps = json.load(f)
        print(f"已加载场景数据: {len(scene_timestamps)} 个场景")

    result = analyze_visuals(args.video, scene_timestamps)

    print("\n--- 结果 ---")
    print(f"  成功:           {result['success']}")
    print(f"  主色调:         {result['dominant_colors']}")
    print(f"  调色板:         {result['color_palette']}")
    print(f"  有字幕:         {result['has_subtitles']}")
    print(f"  宽高比:         {result['aspect_ratio']}")
    print(f"  视频类型:       {result['video_type']}")
    print(f"  平均亮度:       {result['average_luminance']}")

    if not result["success"]:
        print(f"  错误:           {result['error']}")
        sys.exit(1)

    print("\n✅ 视觉分析完成")
