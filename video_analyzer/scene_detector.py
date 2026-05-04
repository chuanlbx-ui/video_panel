"""
scene_detector.py — 模块2：场景切分检测

功能:
  检测视频中镜头切换的位置，返回每个镜头的起始/结束时间。

算法策略（优先级从高到低）:
  1. PySceneDetect (ContentDetector) — 最准确，基于 HSV 直方图差异
  2. FFmpeg scene filter — 回退方案，基于像素亮度变化

后处理:
  - 合并太短的场景（< 2秒的合并到前一个）
  - 太长的场景按 5 秒自动拆分

独立测试:
  python scene_detector.py --video "/path/to/video.mp4"

返回格式:
  [
      {"start": 0.0, "end": 4.5},
      {"start": 4.5, "end": 9.2},
      ...
  ]
"""

import json
import os
import re
import subprocess
import sys


# ============================================================
# 核心函数
# ============================================================

def detect_scenes(video_path: str, threshold: float = 0.3) -> list:
    """
    检测视频的场景切分。

    参数:
        video_path: 视频文件路径
        threshold:  场景变化敏感度 (0.0~1.0, 默认 0.3)
                    - 值越小 → 越敏感 → 更多场景切分
                    - 值越大 → 越保守 → 更少场景切分
                    推荐: talking_head 用 0.4, 快节奏用 0.2

    返回:
        list[dict]: 场景列表，每个元素包含 start/end (秒)
    """
    scenes = []

    # ---- 方法1: 尝试 PySceneDetect ----
    try:
        scenes = _detect_with_pyscenedetect(video_path, threshold)
        if scenes:
            print(f"[scene_detector] PySceneDetect 检测到 {len(scenes)} 个场景")
    except Exception as e:
        print(f"[scene_detector] PySceneDetect 不可用: {e}")

    # ---- 方法2: 回退到 FFmpeg ----
    if not scenes:
        try:
            scenes = _detect_with_ffmpeg(video_path, threshold)
            if scenes:
                print(f"[scene_detector] FFmpeg 检测到 {len(scenes)} 个场景")
        except Exception as e:
            print(f"[scene_detector] FFmpeg 回退也失败: {e}")

    # ---- 方法3: 最低保障 — 整段作为一个场景 ----
    if not scenes:
        duration = _get_duration_fallback(video_path)
        scenes = [{"start": 0.0, "end": duration}]
        print(f"[scene_detector] 回退到整段作为一个场景 ({duration}s)")

    # ---- 后处理: 合并短场景 + 拆分长场景 ----
    scenes = post_process_scenes(scenes)

    return scenes


def post_process_scenes(scenes: list) -> list:
    """
    对检测到的场景进行后处理:
      1. 合并太短的场景（< 2秒的合并到前一个）
      2. 太长的场景按 5 秒拆分

    参数:
        scenes: 原始场景列表 [{"start": ..., "end": ...}, ...]

    返回:
        list: 优化后的场景列表
    """
    if not scenes:
        return scenes

    scenes = merge_short_scenes(scenes, min_duration=2.0)
    scenes = split_long_scenes(scenes, max_duration=5.0)

    return scenes


def merge_short_scenes(scenes: list, min_duration: float = 2.0) -> list:
    """
    合并时长小于 min_duration 的场景到前一个场景。

    参数:
        scenes: 场景列表
        min_duration: 最小场景时长（秒）

    返回:
        list: 合并后的场景列表
    """
    if len(scenes) < 2:
        return scenes

    merged = []
    for scene in scenes:
        duration = scene["end"] - scene["start"]

        if duration < min_duration and merged:
            # 合并到前一个场景
            merged[-1]["end"] = scene["end"]
        else:
            merged.append(dict(scene))

    return merged


def split_long_scenes(scenes: list, max_duration: float = 5.0) -> list:
    """
    将时长超过 max_duration 的场景按固定间隔拆分。

    参数:
        scenes: 场景列表
        max_duration: 最大场景时长（秒）

    返回:
        list: 拆分后的场景列表
    """
    result = []
    for scene in scenes:
        duration = scene["end"] - scene["start"]

        if duration <= max_duration:
            result.append(dict(scene))
        else:
            # 按 max_duration 等分
            num_splits = int(duration // max_duration)
            if duration % max_duration > 0.3:  # 余量大于0.3秒则多切一段
                num_splits += 1

            segment_duration = duration / num_splits
            for i in range(num_splits):
                seg_start = scene["start"] + i * segment_duration
                seg_end = seg_start + segment_duration
                if i == num_splits - 1:
                    seg_end = scene["end"]  # 最后一段对齐到原始结束时间
                result.append({
                    "start": round(seg_start, 2),
                    "end": round(seg_end, 2),
                })

    return result


# ============================================================
# 检测引擎实现
# ============================================================

def _detect_with_pyscenedetect(video_path: str, threshold: float = 0.3) -> list:
    """
    使用 PySceneDetect 的 ContentDetector 检测场景切换。

    参数:
        video_path: 视频文件路径
        threshold: 检测阈值

    返回:
        list[dict]: 场景列表，失败返回空列表
    """
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector

        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video)

        scene_list = scene_manager.get_scene_list()

        # 格式化为统一输出
        scenes = []
        for start, end in scene_list:
            scenes.append({
                "start": round(start.get_seconds(), 2),
                "end": round(end.get_seconds(), 2),
            })

        return scenes

    except ImportError:
        raise RuntimeError("PySceneDetect 未安装")
    except Exception as e:
        raise RuntimeError(f"PySceneDetect 检测失败: {e}")


def _detect_with_ffmpeg(video_path: str, threshold: float = 0.3) -> list:
    """
    使用 FFmpeg scene filter 检测场景切换。

    通过解析 ffmpeg 的 showinfo 输出中 scene 标记的位置来判定。

    参数:
        video_path: 视频文件路径
        threshold: 检测阈值

    返回:
        list[dict]: 场景列表，失败返回空列表
    """
    if not os.path.exists(video_path):
        return []

    # FFmpeg 的 scene 阈值范围是 0~1，但与 PySceneDetect 的阈值含义不同
    # PySceneDetect 默认 0.3 ≈ FFmpeg 0.3~0.4
    ffmpeg_threshold = min(threshold * 1.2, 0.9)  # 略微调高以匹配

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{ffmpeg_threshold})',showinfo",
        "-f", "null",
        "-",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return []

    stderr = proc.stderr

    # 解析 showinfo 输出中的 pts_time
    # 格式: [Parsed_showinfo_0 @ 0x...] pts_time:12.345
    time_pattern = re.compile(r"pts_time:(\d+\.?\d*)")
    timestamps = []

    for line in stderr.split("\n"):
        match = time_pattern.search(line)
        if match:
            try:
                ts = float(match.group(1))
                if ts > 0:  # 排除第一帧 (0.0)
                    timestamps.append(ts)
            except ValueError:
                continue

    # 去重并排序
    timestamps = sorted(set(timestamps))

    if not timestamps:
        return []

    # 获取视频总时长
    duration = _get_duration_fallback(video_path)
    if duration <= 0:
        duration = timestamps[-1] + 10  # 估算

    # 构建场景列表
    scenes = []
    prev_ts = 0.0
    for ts in timestamps:
        if ts - prev_ts > 0.1:  # 过滤掉太接近的切点
            scenes.append({"start": round(prev_ts, 2), "end": round(ts, 2)})
            prev_ts = ts

    # 最后一个场景
    if prev_ts < duration:
        scenes.append({"start": round(prev_ts, 2), "end": round(duration, 2)})

    return scenes


def _get_duration_fallback(video_path: str) -> float:
    """
    使用 FFprobe 快速获取视频时长（回退用）。

    参数:
        video_path: 视频文件路径

    返回:
        float: 视频时长（秒）
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            duration_str = data.get("format", {}).get("duration", "0")
            return round(float(duration_str), 2)
    except Exception:
        pass

    return 0.0


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="视频场景切分检测")
    parser.add_argument("--video", type=str, required=True, help="视频文件路径")
    parser.add_argument("--threshold", type=float, default=0.3, help="检测阈值 (0.0~1.0)")
    parser.add_argument("--min-duration", type=float, default=2.0, help="最小场景时长（秒）")
    parser.add_argument("--max-duration", type=float, default=5.0, help="最大场景时长（秒）")
    args = parser.parse_args()

    print("=" * 60)
    print("scene_detector.py — 独立测试")
    print("=" * 60)

    if not os.path.exists(args.video):
        print(f"[错误] 文件不存在: {args.video}")
        sys.exit(1)

    scenes = detect_scenes(args.video, args.threshold)

    # 后处理
    scenes = merge_short_scenes(scenes, args.min_duration)
    scenes = split_long_scenes(scenes, args.max_duration)

    print(f"\n检测到 {len(scenes)} 个场景:")
    print("-" * 40)
    for i, s in enumerate(scenes):
        duration = s["end"] - s["start"]
        print(f"  #{i+1:2d}  {s['start']:8.2f}s → {s['end']:8.2f}s  (时长: {duration:.2f}s)")

    total = sum(s["end"] - s["start"] for s in scenes)
    print(f"\n总时长: {total:.2f}s")
    print("✅ 场景检测完成")
