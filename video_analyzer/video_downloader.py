"""
video_downloader.py — 模块1：视频下载 & 音频提取 & 元信息获取

功能流程:
  1. 接收视频 URL
  2. 使用 yt-dlp 下载最高 1080p 视频（支持抖音/快手/B站/YouTube/小红书等）
  3. 使用 FFmpeg 提取音频 (16kHz mono WAV)
  4. 使用 FFprobe 获取视频元信息 (分辨率/帧率/时长/编码等)

独立测试:
  python video_downloader.py --url "https://www.youtube.com/watch?v=xxx"

返回格式:
  {
      "video_path": "/path/to/source_video.mp4",
      "audio_path": "/path/to/audio.wav",
      "duration": 45.2,
      "width": 1080,
      "height": 1920,
      "fps": 30,
      "format": "mp4",
      "success": True
  }
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ============================================================
# 核心函数
# ============================================================

def download_video(url: str, output_dir: str) -> dict:
    """
    下载视频并提取音频和元信息。

    参数:
        url: 视频链接（支持 YouTube/B站/抖音/快手/小红书等）
        output_dir: 输出目录（会自动创建）

    返回:
        dict: 包含视频路径、音频路径、时长、分辨率等信息的字典
    """
    # 初始化返回结构
    result = {
        "video_path": "",
        "audio_path": "",
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "format": "",
        "success": False,
        "error": "",
    }

    try:
        # 确保输出目录存在
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # ---- 步骤1: 使用 yt-dlp 下载视频 ----
        # 格式选择: bestvideo ≤1080p + bestaudio, 或 best overall ≤1080p
        output_template = os.path.join(output_dir, "source_video.%(ext)s")

        yt_dlp_cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "-o", output_template,
            "--no-playlist",           # 只下载单视频，不处理播放列表
            "--no-warnings",
            url,
        ]

        print(f"[video_downloader] 下载中: {url}")
        download_result = subprocess.run(
            yt_dlp_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )

        if download_result.returncode != 0:
            error_msg = download_result.stderr.strip()
            # 如果报错信息太短或无内容，用 stdout 补充
            if not error_msg:
                error_msg = download_result.stdout.strip()
            result["error"] = f"yt-dlp 下载失败: {error_msg}"
            return result

        # 获取实际下载的文件路径
        # yt-dlp 正常下载后，文件在 output_dir 下
        video_path = None
        
        # 直接从输出目录查找 source_video.* 文件
        for f in sorted(os.listdir(output_dir)):
            if f.startswith("source_video") and os.path.isfile(os.path.join(output_dir, f)):
                video_path = os.path.join(output_dir, f)
                break

        if not video_path or not os.path.exists(video_path):
            result["error"] = "下载完成但未找到视频文件"
            return result

        result["video_path"] = video_path
        print(f"[video_downloader] 下载完成: {video_path}")

        # ---- 步骤2: 提取元信息 ----
        meta = extract_metadata(video_path)
        if meta["success"]:
            result["duration"] = meta["duration"]
            result["width"] = meta["width"]
            result["height"] = meta["height"]
            result["fps"] = meta["fps"]
            result["format"] = meta["format"]

        # ---- 步骤3: 提取音频 ----
        audio_path = extract_audio(video_path, output_dir)
        if audio_path and os.path.exists(audio_path):
            result["audio_path"] = audio_path
            print(f"[video_downloader] 音频提取完成: {audio_path}")
        else:
            print(f"[video_downloader] 警告: 音频提取失败，继续处理")

        # ---- 步骤4: 清理临时 cookies ----
        _cleanup_temp_cookies(output_dir)

        result["success"] = True
        return result

    except subprocess.TimeoutExpired:
        result["error"] = "下载超时（超过300秒）"
        return result
    except Exception as e:
        result["error"] = f"下载过程异常: {str(e)}"
        return result


def extract_metadata(video_path: str) -> dict:
    """
    使用 FFprobe 提取视频元信息。

    参数:
        video_path: 视频文件路径

    返回:
        dict: 包含 duration/width/height/fps/format 的字典
    """
    result = {
        "duration": 0.0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "format": "",
        "success": False,
        "error": "",
    }

    try:
        if not os.path.exists(video_path):
            result["error"] = f"文件不存在: {video_path}"
            return result

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            video_path,
        ]

        probe_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if probe_result.returncode != 0:
            result["error"] = f"FFprobe 失败: {probe_result.stderr.strip()}"
            return result

        data = json.loads(probe_result.stdout)

        # 提取格式信息
        fmt = data.get("format", {})
        result["format"] = fmt.get("format_name", "")
        duration_str = fmt.get("duration", "0")
        try:
            result["duration"] = round(float(duration_str), 2)
        except (ValueError, TypeError):
            result["duration"] = 0.0

        # 提取视频流信息
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if video_stream:
            result["width"] = video_stream.get("width", 0)
            result["height"] = video_stream.get("height", 0)

            # 尝试多种方式获取 fps
            fps_str = video_stream.get("r_frame_rate", "0/1")
            if fps_str == "0/1":
                fps_str = video_stream.get("avg_frame_rate", "0/1")

            # 解析分数格式 "30000/1001" -> 29.97
            if "/" in fps_str:
                parts = fps_str.split("/")
                try:
                    num = float(parts[0])
                    den = float(parts[1]) if len(parts) > 1 and float(parts[1]) != 0 else 1.0
                    result["fps"] = round(num / den, 3)
                except (ValueError, IndexError, ZeroDivisionError):
                    result["fps"] = 0.0
            else:
                try:
                    result["fps"] = round(float(fps_str), 3)
                except ValueError:
                    result["fps"] = 0.0

        result["success"] = True
        return result

    except subprocess.TimeoutExpired:
        result["error"] = "FFprobe 超时"
        return result
    except json.JSONDecodeError as e:
        result["error"] = f"FFprobe 输出解析失败: {str(e)}"
        return result
    except Exception as e:
        result["error"] = f"元信息提取异常: {str(e)}"
        return result


def extract_audio(video_path: str, output_dir: str) -> str:
    """
    使用 FFmpeg 从视频中提取音频 (16kHz, mono, WAV)。

    参数:
        video_path: 视频文件路径
        output_dir: 输出目录

    返回:
        str: 音频文件路径，失败返回空字符串
    """
    try:
        if not os.path.exists(video_path):
            print(f"[extract_audio] 视频文件不存在: {video_path}")
            return ""

        audio_path = os.path.join(output_dir, "audio.wav")

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ar", "16000",      # 采样率 16kHz
            "-ac", "1",           # 单声道
            "-y",                 # 覆盖已存在文件
            audio_path,
        ]

        subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            return audio_path
        else:
            return ""

    except subprocess.TimeoutExpired:
        print("[extract_audio] 音频提取超时")
        return ""
    except Exception as e:
        print(f"[extract_audio] 异常: {str(e)}")
        return ""


# ============================================================
# 辅助函数
# ============================================================

def _cleanup_temp_cookies(directory: str):
    """
    清理 yt-dlp 下载过程中生成的临时 cookies 文件。
    """
    try:
        for f in os.listdir(directory):
            if f.startswith("cookies") or "cookie" in f.lower():
                fpath = os.path.join(directory, f)
                if os.path.isfile(fpath):
                    os.remove(fpath)
    except Exception:
        pass


def validate_url(url: str) -> bool:
    """
    验证 URL 是否为支持的视频平台链接。

    支持的平台:
      - YouTube (youtube.com, youtu.be)
      - Bilibili (bilibili.com)
      - 抖音 (douyin.com)
      - 快手 (kuaishou.com)
      - 小红书 (xiaohongshu.com)
      - 其他通用视频链接

    参数:
        url: 待验证的链接

    返回:
        bool: 链接是否有效
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False

    # 支持的域名列表
    supported_domains = [
        "youtube.com", "youtu.be",
        "bilibili.com", "b23.tv",
        "douyin.com", "iesdouyin.com",
        "kuaishou.com",
        "xiaohongshu.com",
        "ixigua.com",
        "weibo.com",
        "t.co",  # Twitter/X 视频
    ]

    # 检查是否匹配已知域名
    url_lower = url.lower()
    for domain in supported_domains:
        if domain in url_lower:
            return True

    # 通用检查: 包含 video 或 play 关键词的链接
    if re.search(r"/(video|play|watch|share)/", url_lower):
        return True

    return True  # 放宽限制，让 yt-dlp 自己去判断


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="视频下载 & 音频提取 & 元信息获取")
    parser.add_argument("--url", type=str, required=True, help="视频 URL")
    parser.add_argument("--output", type=str, default="./download_output", help="输出目录")
    args = parser.parse_args()

    print("=" * 60)
    print("video_downloader.py — 独立测试")
    print("=" * 60)

    if not validate_url(args.url):
        print("[错误] URL 格式无效，但继续尝试下载...")

    result = download_video(args.url, args.output)

    print("\n--- 结果 ---")
    print(f"  成功:     {result['success']}")
    print(f"  视频路径: {result['video_path']}")
    print(f"  音频路径: {result['audio_path']}")
    print(f"  时长:     {result['duration']}s")
    print(f"  分辨率:   {result['width']}x{result['height']}")
    print(f"  帧率:     {result['fps']}fps")
    print(f"  格式:     {result['format']}")

    if not result["success"]:
        print(f"  错误:     {result['error']}")
        sys.exit(1)
    else:
        print("\n✅ 下载与分析完成")
