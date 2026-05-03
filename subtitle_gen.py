#!/usr/bin/env python3
"""
字幕生成模块 - Subtitle Generator
将配音文案按标点分片，估算时长，输出标准SRT格式字幕。
支持CLI调用和import调用。
"""

import argparse
import re
import os
import sys
import subprocess
import tempfile
import json
import math


def split_text(text: str) -> list[str]:
    """
    将文本按标点符号分割成片段。
    保留标点符号在片段末尾。
    """
    # 按中文标点分割，保留分隔符
    parts = re.split(r'(?<=[。！？，])', text)
    # 过滤空片段
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def estimate_duration_simple(text: str, chars_per_sec: float = 6.67) -> float:
    """
    简单估算：每字约0.15秒 (≈ 6.67字/秒)
    返回时长（秒）
    """
    # 只计数中文字符和英文字母
    char_count = len(re.findall(r'[\u4e00-\u9fff]', text))
    char_count += len(re.findall(r'[a-zA-Z0-9]', text)) * 0.5  # 英文算半个字
    duration = char_count / chars_per_sec
    # 最短0.5秒
    return max(duration, 0.5)


def estimate_duration_edge_tts(text: str, voice: str = "zh-CN-YunyangNeural") -> float | None:
    """
    使用edge-tts估算音频时长。
    生成一段临时音频，获取其时长。
    返回时长（秒），失败则返回None。
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        result = subprocess.run(
            ["edge-tts", "--voice", voice, "--text", text, "--write-media", tmp_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            os.unlink(tmp_path)
            return None

        # 使用ffprobe获取音频时长
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", tmp_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        os.unlink(tmp_path)

        if probe.returncode == 0 and probe.stdout.strip():
            return float(probe.stdout.strip())

        return None
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return None


def gen_subtitle(text: str, output_path: str | None = None,
                 use_edge_tts: bool = False,
                 voice: str = "zh-CN-YunyangNeural",
                 chars_per_sec: float = 6.67,
                 pause_between: float = 0.1) -> str:
    """
    生成SRT格式字幕。

    参数:
        text: 配音文案
        output_path: 输出文件路径，None则只返回字符串
        use_edge_tts: 是否使用edge-tts精确估算时长
        voice: edge-tts语音名称
        chars_per_sec: 简单估算时的语速（字符/秒），默认6.67 ≈ 0.15秒/字
        pause_between: 片段间停顿（秒）
    返回:
        SRT格式字符串
    """
    fragments = split_text(text)

    if not fragments:
        return ""

    # 估算每个片段的时长
    durations = []
    total_text_len = sum(len(re.findall(r'[\u4e00-\u9fff]', f)) for f in fragments)

    if use_edge_tts and total_text_len > 0:
        # 使用edge-tts逐片段估算
        for frag in fragments:
            dur = estimate_duration_edge_tts(frag, voice)
            if dur is not None:
                durations.append(dur)
            else:
                durations.append(estimate_duration_simple(frag, chars_per_sec))
    else:
        # 使用简单算法
        for frag in fragments:
            durations.append(estimate_duration_simple(frag, chars_per_sec))

    # 生成SRT
    srt_lines = []
    current_time = 0.0

    for i, (frag, dur) in enumerate(zip(fragments, durations)):
        idx = i + 1
        start_sec = current_time
        end_sec = current_time + dur

        # 格式化为 SRT 时间戳: HH:MM:SS,mmm
        start_ts = _format_srt_time(start_sec)
        end_ts = _format_srt_time(end_sec)

        srt_lines.append(str(idx))
        srt_lines.append(f"{start_ts} --> {end_ts}")
        srt_lines.append(frag)
        srt_lines.append("")

        current_time = end_sec + pause_between

    srt_content = "\n".join(srt_lines)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

    return srt_content


def _format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间戳 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _inject_style_srt(srt_content: str, style_css: str = "") -> str:
    """
    注入ASS/SSA样式信息到SRT。
    默认SRT不支持样式，但可用于兼容SSA。
    这里返回原始的SRT，样式信息由播放器或后续处理模块处理。
    """
    # SRT本质不支持样式嵌入，但返回原始即可
    # 额外样式说明以注释方式加在SRT头部
    styled = "/* 字幕样式: 底部居中, 白色字体, 半透明黑底 */\n"
    styled += "/* 请在播放器或渲染时应用此样式 */\n"
    styled += srt_content
    return styled


def main():
    parser = argparse.ArgumentParser(description="字幕生成工具 - 配音文案转SRT字幕")
    parser.add_argument("--text", type=str, required=True,
                        help="配音文案内容")
    parser.add_argument("--output", type=str, default="",
                        help="输出SRT字幕文件路径")
    parser.add_argument("--use-edge-tts", action="store_true",
                        help="使用edge-tts精确估算时长（较慢但更准确）")
    parser.add_argument("--voice", type=str, default="zh-CN-YunyangNeural",
                        help="edge-tts语音名称 (默认: zh-CN-YunyangNeural)")
    parser.add_argument("--speed", type=float, default=6.67,
                        help="语速，字符/秒 (默认: 6.67 ≈ 0.15秒/字)")

    args = parser.parse_args()

    if not args.text:
        print("错误: 请输入文案内容 (--text)", file=sys.stderr)
        sys.exit(1)

    output_path = args.output if args.output else None

    srt_content = gen_subtitle(
        text=args.text,
        output_path=output_path,
        use_edge_tts=args.use_edge_tts,
        voice=args.voice,
        chars_per_sec=args.speed
    )

    if output_path:
        print(f"字幕已生成: {os.path.abspath(output_path)}")
        newline_count = srt_content.count('\n')
        print(f"共 {newline_count // 4 + 1} 条字幕片段")
    else:
        print(srt_content)


if __name__ == "__main__":
    main()
