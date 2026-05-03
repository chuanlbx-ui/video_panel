#!/usr/bin/env python3
"""
build_engine.py — 共享视频构建引擎，由各模板的 build_from_config.py 调用

包含所有通用的辅助函数：配色处理、TTS配音、BGM合成、音频合成、缓存检查等
各模板只需实现自己的 build_html(config) -> str 即可。

使用方式：
    from build_engine import run_build, build_from_config_main
    
    def build_html(config):
        # 模板特有逻辑
        ...
        return html
    
    if __name__ == "__main__":
        # main() 函数会调用 build_html
        pass
    
    或者直接：
    build_from_config_main(build_html, __file__)
"""
import json, sys, subprocess, argparse, os, shutil, re, hashlib, time
from pathlib import Path

# 基础目录
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def find_hyperframes():
    """找 hyperframes 可执行文件"""
    for p in ["npx", "npx.cmd"]:
        if shutil.which(p):
            return p
    return "npx"


def blend_color(c1, c2):
    """简单混合两个颜色"""
    return c2


def darken(c):
    r = max(0, int(c[1:3], 16) - 20)
    g = max(0, int(c[3:5], 16) - 20)
    b = max(0, int(c[5:7], 16) - 20)
    return f'#{r:02x}{g:02x}{b:02x}'


def hex_to_rgb_str(hex_color):
    """#ffd700 -> '255,215,0'"""
    h = hex_color.lstrip("#")
    return f'{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}'


def get_color_scheme(cfg):
    """获取配色方案对象"""
    colors_scheme = cfg.get("colors", {}).get("scheme", "tech_blue")
    colors_opts = cfg.get("colors", {}).get("options", [])
    cs = colors_opts[0] if colors_opts else {
        "bg_top": "#0a1628", "bg_bottom": "#0d1f3c",
        "white_text": "#fff", "gold_text": "#ffd700",
        "cyan_text": "#00d4ff", "subtitle_color": "rgba(255,255,255,0.5)"
    }
    for opt in colors_opts:
        if opt["id"] == colors_scheme:
            cs = opt
            break
    return cs


def generate_tts(config, template_dir):
    """生成TTS配音文件 — 使用edge-tts"""
    audio_cfg = config.get("audio", {})
    vo_cfg = audio_cfg.get("voiceover", {})
    if not vo_cfg.get("enabled", False):
        return None

    text = vo_cfg.get("text", "").strip()
    if not text:
        return None

    voice = vo_cfg.get("voice", vo_cfg.get("default_voice", "zh-CN-YunyangNeural"))
    rate = vo_cfg.get("rate", "+0%")

    tts_output = template_dir / "voiceover.wav"
    if tts_output.exists():
        tts_output.unlink()

    cmd = ["edge-tts", "--voice", voice, f"--rate={rate}",
           "--text", text, "--write-media", str(tts_output)]
    print(f"TTS: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"TTS警告: {r.stderr[:200]}")
        return None

    if tts_output.exists():
        print(f"TTS生成: {tts_output} ({tts_output.stat().st_size} bytes)")
        return tts_output
    return None


def get_audio_duration(audio_path):
    """获取音频时长"""
    if not audio_path or not audio_path.exists():
        return 28
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                        str(audio_path)], capture_output=True, text=True, timeout=10)
    try:
        return float(r.stdout.strip())
    except:
        return 28


def merge_audio(video_path, voiceover_path, bgm_path, bgm_volume, output_path):
    """用FFmpeg合成视频+配音+BGM"""
    if not voiceover_path and not bgm_path:
        return video_path

    import tempfile

    filters = []
    inputs = []
    input_idx = 0

    inputs.append(str(video_path))
    video_idx = input_idx
    input_idx += 1

    audio_streams = []

    if voiceover_path and voiceover_path.exists():
        inputs.append(str(voiceover_path))
        audio_streams.append(f"[{input_idx}:a]adelay=0|0[a{input_idx}]")
        input_idx += 1

    if bgm_path and bgm_path.exists():
        inputs.append(str(bgm_path))
        dur = get_audio_duration(voiceover_path) if voiceover_path else 28
        audio_streams.append(f"[{input_idx}:a]volume={bgm_volume},aloop=loop=-1:size=0,atrim=duration={dur}[a{input_idx}]")
        input_idx += 1

    if len(audio_streams) == 1:
        m = re.findall(r'\[([^\]]+)\]', audio_streams[0])
        out_label = f"[{m[-1]}]" if m else "[a1]"
        mix_filter = audio_streams[0]
        map_str = out_label
    elif len(audio_streams) == 2:
        s1_label = re.findall(r'\[([^\]]+)\]', audio_streams[0])[-1]
        s2_label = re.findall(r'\[([^\]]+)\]', audio_streams[1])[-1]
        s1_label_b = f"[{s1_label}]"
        s2_label_b = f"[{s2_label}]"
        mix_filter = f"{audio_streams[0]};{audio_streams[1]};{s1_label_b}{s2_label_b}amix=inputs=2:duration=first[aout]"
        map_str = "[aout]"
    else:
        mix_filter = ""
        map_str = ""

    filter_parts = [mix_filter] if mix_filter else audio_streams
    filter_complex = ";".join(filter_parts) if filter_parts else ""

    cmd = ["ffmpeg", "-y"]
    for inp in inputs:
        cmd.extend(["-i", inp])

    if filter_complex:
        cmd.extend(["-filter_complex", filter_complex,
                    "-map", f"{video_idx}:v", "-map", map_str])

    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(output_path)])

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"音视频合成失败:")
        print(f"  命令: {' '.join(str(x) for x in cmd[:15])}")
        print(f"  错误: {r.stderr[:500]}")
        return video_path

    print(f"合成完成: {output_path}")
    return output_path


def download_bgm(template_dir, bgm_id):
    """下载/准备BGM文件"""
    bgm_dir = template_dir / "bgm"
    bgm_dir.mkdir(exist_ok=True)

    bgm_files = {
        "tech_pulse": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "uplifting": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "ambient": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
    }

    if bgm_id in bgm_files:
        dst = bgm_dir / f"{bgm_id}.mp3"
        if not dst.exists():
            import urllib.request
            try:
                print(f"下载BGM: {bgm_id}")
                urllib.request.urlretrieve(bgm_files[bgm_id], dst)
                print(f"  -> {dst}")
            except Exception as e:
                print(f"BGM下载失败: {e}")
                return None
        return dst
    return None


def check_cache(config, cache_key=None):
    """检查是否有有效的缓存文件"""
    if cache_key is None:
        cache_key = hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()
    cache_path = OUTPUT_DIR / f"cache_{cache_key}.mp4"
    if cache_path.exists():
        cache_age = time.time() - cache_path.stat().st_mtime
        if cache_age < 7 * 86400:
            return cache_path
        else:
            cache_path.unlink(missing_ok=True)
    return None


def build_from_config_main(build_html_func, script_path=None, skip_build_html=False):
    """
    标准入口函数，供各模板的 build_from_config.py 调用
    
    参数:
        build_html_func: 生成HTML的函数，签名 build_html(config) -> str
        script_path: 脚本路径（通常是 __file__）
        skip_build_html: 如果为True，跳过HTML生成（仅渲染）
    """
    parser = argparse.ArgumentParser(description="从配置JSON生成hyperframes视频")
    parser.add_argument("--config", default="template_config.json")
    parser.add_argument("--output", default="index.html")
    parser.add_argument("-q", "--quality", default=None, help="渲染质量 (draft/standard/high/pro)")
    parser.add_argument("--render", action="store_true", help="生成后直接渲染+音频合成")
    parser.add_argument("--skip-html", action="store_true", help="跳过HTML生成，仅渲染")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置不存在: {config_path}")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    cwd = config_path.parent

    # 1) 生成HTML
    if not args.skip_html and build_html_func:
        html = build_html_func(config)
        output_path = cwd / args.output
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML已生成: {output_path}")

    # 2) lint
    print("运行 hyperframes lint...")
    npx = find_hyperframes()
    r = subprocess.run([npx, "hyperframes", "lint"],
                       capture_output=True, text=True, timeout=30, cwd=str(cwd))
    if r.returncode == 0:
        print("lint 通过 ✓")
    else:
        print(f"lint: {r.stdout[:300]}")

    if not args.render:
        return

    # 3) 渲染视频
    settings = config.get("settings", {})
    quality = args.quality or settings.get("quality", "standard")
    bitrate = settings.get("video_bitrate", "15M")
    fps = settings.get("fps", 30)

    # 命令行参数优先级高于config
    if args.quality == "draft" or quality == "draft":
        quality = "draft"
        bitrate = "5M"
        fps = 24  # hyperframes最低支持24fps

    raw_output = cwd / "raw_output.mp4"
    render_cmd = [npx, "hyperframes", "render",
                  "-o", str(raw_output),
                  "-f", str(fps),
                  "-q", quality,
                  "-w", "auto",
                  "--video-bitrate", bitrate]
    if raw_output.exists():
        raw_output.unlink()

    print(f"渲染中... (quality={quality}, {bitrate}, {fps}fps)")
    r = subprocess.run(render_cmd, timeout=600, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode != 0:
        print(f"渲染失败: {r.stderr[:500]}")
        sys.exit(1)
    print(f"渲染完成: {raw_output}")

    # 4) TTS配音
    voiceover_path = generate_tts(config, cwd)

    # 5) BGM 准备
    audio_cfg = config.get("audio", {})
    bgm_cfg = audio_cfg.get("bgm", {})
    bgm_path = None
    if bgm_cfg.get("enabled", False):
        bgm_id = bgm_cfg.get("file", "")
        if bgm_id and bgm_id != "none":
            local_bgm = cwd / "bgm" / f"{bgm_id}.mp3"
            if local_bgm.exists():
                bgm_path = local_bgm
                print(f"BGM: {bgm_path}")
            else:
                bgm_path = download_bgm(cwd, bgm_id)

    # 6) 合成音频
    if voiceover_path or bgm_path:
        final_output = cwd / "output_final.mp4"
        merge_audio(raw_output, voiceover_path, bgm_path,
                    bgm_cfg.get("volume", 0.3), final_output)
        print(f"最终视频: {final_output}")
    else:
        final_output = raw_output

    # 复制到output目录
    output_dir = cwd.parent / "output"
    output_dir.mkdir(exist_ok=True)
    shutil.copy(final_output, output_dir / "output.mp4")
    print(f"已复制到: {output_dir}/output.mp4")

    # 清理临时TTS输入
    tts_txt = cwd / "tts_input.txt"
    if tts_txt.exists():
        tts_txt.unlink()
