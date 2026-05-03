#!/usr/bin/env python3
"""
将 template_config.json 转换为 hyperframes index.html + TTS配音 + BGM合成

协会活动邀请函（横版16:9）1920×1080，红金庆典风格，3场景结构。

用法：
  python3 build_from_config.py [--config template_config.json] [--output index.html] [--render]
  python3 build_from_config.py --render   # 生成后直接渲染+合成音频

v2.1: 支持pro画质（20M码率）+ 特效参数（transition_style, particle_density）
"""
import json, sys, os
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from layout_randomizer import apply_random_jitter
from build_engine import (build_from_config_main, get_color_scheme, 
                          blend_color, darken, hex_to_rgb_str)

def build_html(config):
    cfg = config
    scenes = cfg["scenes"]
    w, h = cfg["settings"]["output_width"], cfg["settings"]["output_height"]

    # 配色方案
    colors_scheme = cfg.get("colors", {}).get("scheme", "red_gold")
    colors_opts = cfg.get("colors", {}).get("options", [])
    cs = colors_opts[0] if colors_opts else {"bg_top": "#1a0000", "bg_bottom": "#2d0a00",
                                               "white_text": "#fff", "gold_text": "#ffd700",
                                               "cyan_text": "#ff6b35", "subtitle_color": "rgba(255,215,0,0.5)"}
    for opt in colors_opts:
        if opt["id"] == colors_scheme:
            cs = opt
            break

    # 动画风格
    anim_style = cfg.get("animation", {}).get("style", "standard")

    # 特效参数
    effects = cfg.get("effects", {})
    transition_style = effects.get("transition_style", "fade")
    particle_density = effects.get("particle_density", "medium")
    glow_enabled = effects.get("glow_enabled", False)

    bg_top, bg_bottom = cs["bg_top"], cs["bg_bottom"]
    col_white, col_gold, col_cyan = cs["white_text"], cs["gold_text"], cs["cyan_text"]
    col_sub = cs["subtitle_color"]

    # 场景渐变（横版宽屏用 radial 更适合）
    gradient_s1 = f"radial-gradient(ellipse at center, {bg_top} 0%, {bg_bottom} 50%, {darken(bg_top)} 100%)"
    gradient_s2 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 40%, {darken(bg_top)} 100%)"
    gradient_s3 = f"radial-gradient(ellipse at center bottom, {bg_bottom} 0%, {bg_top} 60%, {darken(bg_top)} 100%)"

    # 粒子颜色（横版密度的计算）
    particle_c1 = f"rgba({hex_to_rgb_str(col_gold)},0.15)"
    particle_c2 = f"rgba({hex_to_rgb_str(col_cyan)},0.12)"

    # 粒子数量按密度调整
    particle_count_map = {"low": 8, "medium": 15, "high": 25}
    n_particles = particle_count_map.get(particle_density, 15)

    # 转场CSS
    transition_class = ""
    if transition_style == "fade":
        transition_class = "transition: opacity 0.5s ease;"
    elif transition_style == "slide":
        transition_class = "transition: transform 0.6s ease, opacity 0.6s ease;"
    elif transition_style == "zoom":
        transition_class = "transition: transform 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94), opacity 0.6s ease;"

    # 辉光效果
    glow_css = ""
    if glow_enabled:
        glow_css = """
.scene::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(ellipse at 50% 30%, rgba(255,215,0,0.03) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}"""

    # 构建场景HTML + 时间轴
    scenes_html = ""
    tl_lines = []

    for idx, sc in enumerate(scenes):
        elems_html = ""
        for key, val in sc.get("elements", {}).items():
            st = val.get("style", "")
            tx = val.get("text", "")
            elems_html += f'    <div class="{st}" id="{sc["id"]}_{key}">{tx}</div>\n'

        scenes_html += (
            f'  <!-- ===== {sc["name"]} ({sc["start"]}-{sc["start"]+sc["duration"]}s) ===== -->\n'
            f'  <div id="{sc["id"]}" class="scene" data-start="{sc["start"]}" data-duration="{sc["duration"]}">\n'
            f'    <div class="particles" id="p{idx+1}"></div>\n'
            f'{elems_html}  </div>\n\n'
        )

        # 动画时间轴
        t = sc["start"]
        for key in sc.get("elements", {}):
            eid = f'"{sc["id"]}_{key}"'

            if anim_style == "scale":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,scale:0.5,duration:0.5,ease:"back.out(1.7)"}},{t});')
            elif anim_style == "glitch":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,x:-10,duration:0.15}},{t});')
                tl_lines.append(f'  tl.to({eid}, {{opacity:1,x:0,duration:0.1}},{t}+0.15);')
            elif anim_style == "slide":
                side = "x:-80" if idx % 2 == 0 else "x:80"
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,{side},duration:0.5,ease:"power2.out"}},{t});')
            else:  # standard
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,y:60,duration:0.6}},{t});')

            t += 0.6

    tl_js = "\n".join(tl_lines)
    dur = cfg["settings"].get("video_duration", 25)
    n_scenes = len(scenes)

    html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={w}, height={h}" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@700;900&family=Noto+Serif+SC:wght@700;900&display=swap" rel="stylesheet">
  <style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {w}px; height: {h}px; overflow: hidden; background: {bg_top}; font-family: 'Noto Sans SC', sans-serif; }}

.scene {{
  position: absolute; top: 0; left: 0;
  width: {w}px; height: {h}px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  overflow: hidden;
  {transition_class}
}}
#s1 {{ background: {gradient_s1}; }}
#s2 {{ background: {gradient_s2}; }}
#s3 {{ background: {gradient_s3}; }}

.large_white {{ font-weight: 900; font-size: 90px; color: {col_white}; text-shadow: 0 0 60px rgba(100,180,255,0.3); text-align: center; }}
.large_gold {{ font-weight: 900; font-size: 100px; color: {col_gold}; text-shadow: 0 0 50px rgba(255,215,0,0.3); text-align: center; }}
.large_cyan {{ font-weight: 900; font-size: 90px; color: {col_cyan}; text-shadow: 0 0 50px rgba(0,212,255,0.3); text-align: center; }}
.subtitle {{ font-weight: 700; font-size: 36px; color: {col_sub}; margin-top: 30px; letter-spacing: 4px; }}
.bullet {{ font-weight: 700; font-size: 48px; color: {col_gold}; margin: 15px 0; text-align: center; line-height: 1.5; text-shadow: 0 0 20px rgba(255,215,0,0.2); }}
.price {{ font-weight: 900; font-size: 90px; color: {col_gold}; text-shadow: 0 0 60px rgba(255,215,0,0.5); }}
.info {{ font-family: 'Noto Sans SC', sans-serif; font-weight: 700; font-size: 40px; color: #fff; text-align: center; line-height: 1.6; margin-top: 20px; }}
.phone {{ font-weight: 900; font-size: 40px; color: {col_cyan}; margin-top: 30px; text-shadow: 0 0 20px rgba(0,212,255,0.3); }}
.particles {{ position: absolute; top:0; left:0; right:0; bottom:0; pointer-events:none; }}
.dot {{ position: absolute; border-radius: 50%; width: 3px; height: 3px; }}
{glow_css}
  </style>
</head>
<body>

<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">

{scenes_html}</div>

<script>
  window.__timelines = window.__timelines || {{}};
  const tl = gsap.timeline({{ paused: true }});

{tl_js}
  function mkParticles(id) {{
    const c = document.getElementById(id);
    if (!c) return;
    for (let i = 0; i < {n_particles}; i++) {{
      const d = document.createElement('div');
      d.className = 'dot';
      d.style.left = (Math.random() * 95) + '%';
      d.style.top = (Math.random() * 95) + '%';
      d.style.background = Math.random() > 0.5 ? '{particle_c1}' : '{particle_c2}';
      c.appendChild(d);
    }}
  }}
  for (let i = 1; i <= {n_scenes}; i++) mkParticles('p' + i);

  window.__timelines["main"] = tl;
</script>
</body>
</html>"""
    # 动态排版随机感 — 注入确定性伪随机抖动
    jitter_cfg = config.get("_jitter", {}).get("enabled", False)
    if jitter_cfg:
        j_seed = config["_jitter"].get("job_seed", hash(str(config)))
        html = apply_random_jitter(
            html,
            rnd_seed=j_seed,
            font_range=config["_jitter"].get("font_size_range", 2),
            margin_pct=config["_jitter"].get("margin_top_range_pct", 5.0),
            particle_min=config["_jitter"].get("particle_mult_min", 0.7),
            particle_max=config["_jitter"].get("particle_mult_max", 1.3),
        )

    return html

    text = vo_cfg.get("text", "").strip()
    if not text:
        return None

    voice = vo_cfg.get("voice", vo_cfg.get("default_voice", "zh-CN-YunyangNeural"))

    # kokoro声音ID到edge-tts声音ID的映射
    kokoro_to_edge = {
        "zf_xiaobei": "zh-CN-liaoning-XiaobeiNeural",
        "zf_xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "zf_xiaoni": "zh-CN-shaanxi-XiaoniNeural",
        "zm_yunxia": "zh-CN-YunxiaNeural",
        "zm_yunyang": "zh-CN-YunyangNeural",
        "zm_yunjian": "zh-CN-YunjianNeural",
        "zm_yunxi": "zh-CN-YunxiNeural",
    }
    edge_voice = kokoro_to_edge.get(voice, voice)

    rate = "-10%"  # 默认慢速更稳重

    tts_output = template_dir / "voiceover.wav"
    if tts_output.exists():
        tts_output.unlink()

    # 使用edge-tts生成
        # 使用edge-tts生成（用-f从文件读文本，避免引号/换行问题）
    txt_file = template_dir / "tts_input.txt"
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(text)
    cmd = ["edge-tts", "--voice", edge_voice, f"--rate={rate}",
           "-f", str(txt_file), "--write-media", str(tts_output)]
    print(f"TTS: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"TTS警告: {r.stderr[:200]}")
        return None

    if tts_output.exists():
        print(f"TTS生成: {tts_output} ({tts_output.stat().st_size} bytes)")
        return tts_output
    return None

    import tempfile

    filters = []
    inputs = []
    input_idx = 0

    # 视频（取原音频）
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
        # BGM循环+音量调节
        audio_streams.append(f"[{input_idx}:a]volume={bgm_volume},aloop=loop=-1:size=0,atrim=duration={dur}[a{input_idx}]")
        input_idx += 1

    # 构建filter图
    if len(audio_streams) == 1:
        # 只有一个音频流: 提取输出标签 [aN]
        as0 = audio_streams[0]
        import re
        m = re.findall(r'\[([^\]]+)\]', as0)
        out_label = f"[{m[-1]}]" if m else "[a1]"
        mix_filter = as0
        map_str = out_label
    elif len(audio_streams) == 2:
        import re
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
def main():
    build_from_config_main(build_html, script_path=__file__)


if __name__ == "__main__":
    main()
