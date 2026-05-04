"""
speech_analyzer.py — 模块3：语音转文字 (Whisper)

功能:
  使用 Whisper 模型将音频口播转为带时间戳的文字。

支持的引擎（优先级）:
  1. faster-whisper — 速度更快，支持 GPU
  2. openai-whisper — 回退方案

策略:
  - 默认 model_size="small"（平衡速度和准确率）
  - 设置 language="zh" 提升中文准确率
  - 音频超过 5 分钟则只分析前 3 分钟（防止超时）

独立测试:
  python speech_analyzer.py --audio "/path/to/audio.wav"

返回格式:
  {
      "full_text": "大家好，今天我们来聊一聊...",
      "segments": [
          {"start": 0.0, "end": 3.5, "text": "大家好"},
          {"start": 3.5, "end": 7.2, "text": "今天我们来聊一聊"}
      ],
      "duration": 45.2,
      "speech_speed": 3.5,   # 字/秒
      "success": True
  }
"""

import os
import sys
import time


# ============================================================
# 核心函数
# ============================================================

def analyze_speech(audio_path: str, model_size: str = "small") -> dict:
    """
    使用 Whisper 进行语音转文字分析。

    参数:
        audio_path: 音频文件路径 (WAV 格式, 16kHz 最佳)
        model_size: 模型大小 ("tiny", "small", "medium", "large")
                    - tiny:   最快，准确率略低 (~1GB VRAM)
                    - small:  平衡速度和准确率 (~2GB VRAM) ★推荐
                    - medium: 更准确但更慢 (~5GB VRAM)
                    - large:  最准确但最慢 (~10GB VRAM)

    返回:
        dict: 包含完整文本、时间戳段落、语速等信息的字典
    """
    result = {
        "full_text": "",
        "segments": [],
        "duration": 0.0,
        "speech_speed": 0.0,
        "success": False,
        "error": "",
    }

    # 校验输入
    if not audio_path or not os.path.exists(audio_path):
        result["error"] = f"音频文件不存在: {audio_path}"
        return result

    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        result["error"] = "音频文件为空"
        return result

    try:
        print(f"[speech_analyzer] 加载 Whisper 模型 (size={model_size})...")

        # ---- 方法1: faster-whisper ----
        segments, info = _transcribe_faster_whisper(audio_path, model_size)

        # ---- 方法2: 回退到 openai-whisper ----
        if not segments:
            print("[speech_analyzer] faster-whisper 不可用，回退到 openai-whisper...")
            segments, info = _transcribe_openai_whisper(audio_path, model_size)

        # ---- 处理结果 ----
        if not segments:
            result["error"] = "所有 Whisper 引擎均无法转录"
            return result

        # 音频时长
        audio_duration = info.get("duration", 0.0)
        result["duration"] = round(audio_duration, 2)

        # 拼接全文
        full_text_parts = []
        for seg in segments:
            full_text_parts.append(seg["text"])
        full_text = "".join(full_text_parts)
        result["full_text"] = full_text.strip()

        # 计算语速 (字/秒)
        char_count = len(full_text.replace(" ", "").replace("\n", ""))
        if audio_duration > 0:
            result["speech_speed"] = round(char_count / audio_duration, 2)
        else:
            result["speech_speed"] = 0.0

        result["segments"] = segments
        result["success"] = True

        print(f"[speech_analyzer] 转录完成: {char_count} 字, {audio_duration:.1f}s, {result['speech_speed']} 字/秒")
        return result

    except Exception as e:
        result["error"] = f"语音分析异常: {str(e)}"
        return result


def compute_speech_speed(full_text: str, duration: float) -> float:
    """
    计算语速（字/秒）。

    参数:
        full_text: 完整口播文本
        duration: 音频时长（秒）

    返回:
        float: 每秒字数
    """
    if duration <= 0:
        return 0.0
    char_count = len(full_text.replace(" ", "").replace("\n", ""))
    return round(char_count / duration, 2)


# ============================================================
# 引擎实现
# ============================================================

def _transcribe_faster_whisper(audio_path: str, model_size: str) -> tuple:
    """
    使用 faster-whisper 进行转录。

    参数:
        audio_path: 音频路径
        model_size: 模型大小

    返回:
        tuple: (segments_list, info_dict)
            segments: [{"start": 0.0, "end": 3.5, "text": "..."}, ...] 或 None
            info: {"duration": 45.2, "language": "zh"}
    """
    try:
        from faster_whisper import WhisperModel

        # 确定计算设备
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
        else:
            device = "cpu"
            compute_type = "int8"

        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        # 配置转录参数
        # language="zh" 强制中文模式，提高准确率
        # 音频 > 5分钟时限制处理前 3分钟
        audio_duration = _get_audio_duration(audio_path)
        clip_start = 0
        clip_end = None

        if audio_duration > 300:  # 5分钟
            clip_end = 180  # 只分析前3分钟
            print(f"[speech_analyzer] 音频过长 ({audio_duration:.0f}s)，仅分析前 180s")

        segment_generator, info = model.transcribe(
            audio_path,
            language="zh",
            beam_size=5,
            vad_filter=True,           # 语音活动检测，过滤静音
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt="以下是普通话的语音转录",
        )

        segments = []
        for seg in segment_generator:
            # 如果限制了时长，跳过超出部分
            if clip_end is not None and seg.end > clip_end:
                if seg.start < clip_end:
                    # 截断
                    segments.append({
                        "start": round(seg.start, 2) if seg.start >= 0 else 0.0,
                        "end": round(float(clip_end), 2),
                        "text": seg.text.strip(),
                    })
                break

            segments.append({
                "start": round(seg.start, 2) if seg.start >= 0 else 0.0,
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })

        info_dict = {
            "duration": round(info.duration, 2) if info.duration else audio_duration,
            "language": info.language if info.language else "zh",
        }

        return segments, info_dict

    except ImportError:
        return None, {"duration": 0.0, "language": "zh"}
    except Exception as e:
        print(f"[speech_analyzer] faster-whisper 出错: {e}")
        return None, {"duration": 0.0, "language": "zh"}


def _transcribe_openai_whisper(audio_path: str, model_size: str) -> tuple:
    """
    使用 openai-whisper 进行转录（回退方案）。

    参数:
        audio_path: 音频路径
        model_size: 模型大小

    返回:
        tuple: (segments_list, info_dict)
    """
    try:
        import whisper

        model = whisper.load_model(model_size)

        # 音频 > 5分钟时限制
        audio_duration = _get_audio_duration(audio_path)
        clip_end = None
        if audio_duration > 300:
            clip_end = 180
            print(f"[speech_analyzer] 音频过长 ({audio_duration:.0f}s)，仅分析前 180s")

        result_raw = model.transcribe(
            audio_path,
            language="zh",
            initial_prompt="以下是普通话的语音转录",
        )

        segments = []
        for seg in result_raw.get("segments", []):
            seg_start = seg.get("start", 0.0)
            seg_end = seg.get("end", 0.0)

            if clip_end is not None and seg_start >= clip_end:
                break
            if clip_end is not None and seg_end > clip_end:
                seg_end = float(clip_end)

            segments.append({
                "start": round(seg_start, 2),
                "end": round(seg_end, 2),
                "text": seg.get("text", "").strip(),
            })

        info_dict = {
            "duration": round(audio_duration, 2),
            "language": result_raw.get("language", "zh"),
        }

        return segments, info_dict

    except ImportError:
        return None, {"duration": 0.0, "language": "zh"}
    except Exception as e:
        print(f"[speech_analyzer] openai-whisper 出错: {e}")
        return None, {"duration": 0.0, "language": "zh"}


def _get_audio_duration(audio_path: str) -> float:
    """
    使用 FFprobe 获取音频时长。

    参数:
        audio_path: 音频文件路径

    返回:
        float: 时长（秒）
    """
    import json
    import subprocess

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except Exception:
        pass

    return 0.0


# ============================================================
# 独立测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Whisper 语音转文字分析")
    parser.add_argument("--audio", type=str, required=True, help="音频文件路径 (WAV)")
    parser.add_argument("--model", type=str, default="small", choices=["tiny", "small", "medium", "large"],
                        help="Whisper 模型大小")
    args = parser.parse_args()

    print("=" * 60)
    print("speech_analyzer.py — 独立测试")
    print("=" * 60)

    if not os.path.exists(args.audio):
        print(f"[错误] 文件不存在: {args.audio}")
        sys.exit(1)

    start_time = time.time()
    result = analyze_speech(args.audio, args.model)
    elapsed = time.time() - start_time

    print(f"\n--- 结果 ---")
    print(f"  成功:     {result['success']}")
    print(f"  全文:     {result['full_text'][:200]}{'...' if len(result['full_text']) > 200 else ''}")
    print(f"  段落数:   {len(result['segments'])}")
    print(f"  时长:     {result['duration']}s")
    print(f"  语速:     {result['speech_speed']} 字/秒")
    print(f"  耗时:     {elapsed:.1f}s")

    if not result["success"]:
        print(f"  错误:     {result['error']}")
        sys.exit(1)

    # 打印详细段落
    print(f"\n--- 详细段落 ---")
    for i, seg in enumerate(result["segments"][:20]):  # 只显示前20段
        print(f"  #{i+1:2d}  [{seg['start']:6.2f}s → {seg['end']:6.2f}s] {seg['text']}")

    if len(result["segments"]) > 20:
        print(f"  ... 还有 {len(result['segments'])-20} 段")

    print("\n✅ 语音分析完成")
