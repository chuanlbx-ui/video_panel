#!/usr/bin/env python3
"""
将 template_config.json 转换为 hyperframes index.html + TTS配音 + BGM合成

小红书风格（3:4竖版知识卡片）1080×1440，3场景信息卡片式排版。

用法：
  python3 build_from_config.py [--config template_config.json] [--output index.html] [--render]
  python3 build_from_config.py --render   # 生成后直接渲染+合成音频

v3.0: 支持配色方案、动画风格、edge-tts配音、BGM合成、字幕系统、多种背景类型
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
    colors_scheme = cfg.get("colors", {}).get("scheme", "minimal_white")
    colors_opts = cfg.get("colors", {}).get("options", [])
    cs = colors_opts[0] if colors_opts else {
        "bg_top": "#f5f5f5", "bg_bottom": "#ffffff",
        "white_text": "#1a1a1a", "gold_text": "#c9a84c",
        "cyan_text": "#2c7a9e", "subtitle_color": "rgba(0,0,0,0.4)"
    }
    for opt in colors_opts:
        if opt["id"] == colors_scheme:
            cs = opt
            break

    # 动画风格
    anim_style = cfg.get("animation", {}).get("style", "standard")

    # 背景类型
    bg_type = cfg.get("settings", {}).get("bg_type",
                     cfg.get("background", {}).get("type", "gradient"))

    # 字幕配置
    sub_cfg = cfg.get("subtitles", {})

    bg_top, bg_bottom = cs["bg_top"], cs["bg_bottom"]
    col_white, col_gold, col_cyan = cs["white_text"], cs["gold_text"], cs["cyan_text"]
    col_sub = cs["subtitle_color"]

    # 场景渐变（竖版卡片风格 — 柔和的从上到下渐变）
    gradient_s1 = f"linear-gradient(180deg, {bg_top} 0%, {bg_bottom} 100%)"
    gradient_s2 = f"linear-gradient(180deg, {blend_color(bg_bottom, bg_top)} 0%, {bg_bottom} 100%)"
    gradient_s3 = f"linear-gradient(180deg, {bg_top} 0%, {blend_color(bg_bottom, bg_top)} 100%)"

    # 粒子颜色
    particle_c1 = f"rgba({hex_to_rgb_str(col_gold)},0.10)"
    particle_c2 = f"rgba({hex_to_rgb_str(col_cyan)},0.08)"

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
            f'  <div id="{sc["id"]}" class="scene clip" data-start="{sc["start"]}" data-duration="{sc["duration"]}">\n'
            f'    <div class="particles" id="p{idx+1}"></div>\n'
            f'    <div class="card-wrapper">\n'
            f'{elems_html}    </div>\n'
            f'  </div>\n\n'
        )

        # 动画时间轴
        t = sc["start"]
        for key in sc.get("elements", {}):
            eid = f'"{sc["id"]}_{key}"'
            name = sc["name"]

            if anim_style == "scale":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,scale:0.5,duration:0.5,ease:"back.out(1.7)"}},{t});')
            elif anim_style == "glitch":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,x:-10,duration:0.15}},{t});')
                tl_lines.append(f'  tl.to({eid}, {{opacity:1,x:0,duration:0.1}},{t}+0.15);')
            elif anim_style == "slide":
                side = "x:-60" if idx % 2 == 0 else "x:60"
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,{side},duration:0.5,ease:"power2.out"}},{t});')
            else:  # standard
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,y:40,duration:0.6}},{t});')

            t += 0.5

    tl_js = "\n".join(tl_lines)
    dur = cfg["settings"].get("video_duration", 25)
    n_scenes = len(scenes)

    # 字幕HTML（CSS overlay方式）
    sub_html = ""
    if sub_cfg.get("enabled", False):
        sub_font_size = sub_cfg.get("font_size", 32)
        sub_color = sub_cfg.get("color", "#ffffff")
        sub_bg_opacity = sub_cfg.get("bg_opacity", 0.5)
        for idx, sc in enumerate(scenes):
            sub_text = ""
            if "narration" in sc:
                sub_text = sc["narration"]
            elif "sub" in sc.get("elements", {}):
                sub_text = sc["elements"]["sub"]["text"]
            if sub_text:
                sub_html += f'    <div class="subtitle-overlay clip" id="sub_{sc["id"]}" data-start="{sc["start"]}" data-duration="{sc["duration"]}">{sub_text}</div>\n'

    html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={w}, height={h}" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&family=Noto+Serif+SC:wght@700;900&display=swap" rel="stylesheet">
  <style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {w}px; height: {h}px; overflow: hidden; background: {bg_top}; font-family: 'Noto Sans SC', sans-serif; }}

.scene {{
  position: absolute; top: 0; left: 0;
  width: {w}px; height: {h}px;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  overflow: hidden;
}}
#s1 {{ background: {gradient_s1}; }}
#s2 {{ background: {gradient_s2}; }}
#s3 {{ background: {gradient_s3}; }}

/* 卡片容器 — 小红书风格圆角卡片 */
.card-wrapper {{
  background: rgba(255,255,255,0.92);
  border-radius: 32px;
  padding: 60px 50px;
  margin: 0 40px;
  width: calc(100% - 80px);
  max-width: 920px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.08);
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  text-align: center;
}}

/* 深色主题时卡片变暗 */
#s1 .card-wrapper, #s2 .card-wrapper, #s3 .card-wrapper {{
  background: rgba(255,255,255,0.95);
}}

.large_white {{ font-weight: 900; font-size: 96px; color: {col_white}; margin-bottom: 20px; line-height: 1.3; }}
.large_gold {{ font-weight: 900; font-size: 96px; color: {col_gold}; margin-bottom: 20px; line-height: 1.3; }}
.large_cyan {{ font-weight: 900; font-size: 96px; color: {col_cyan}; margin-bottom: 20px; line-height: 1.3; }}
.subtitle {{ font-weight: 400; font-size: 38px; color: {col_sub}; margin-top: 10px; letter-spacing: 4px; }}
.tags {{ font-weight: 700; font-size: 52px; color: {col_gold}; line-height: 1.5; }}
.price {{ font-weight: 900; font-size: 80px; color: {col_gold}; text-shadow: 0 0 40px rgba(201,168,76,0.3); }}
.info {{ font-weight: 400; font-size: 36px; color: {col_sub}; text-align: center; line-height: 1.6; margin-top: 20px; }}
.bullet {{ font-weight: 700; font-size: 42px; color: {col_white}; line-height: 1.8; margin: 8px 0; padding: 10px 20px; background: rgba({hex_to_rgb_str(col_cyan)},0.06); border-radius: 12px; width: 100%; }}
.phone {{ font-weight: 700; font-size: 42px; color: {col_cyan}; margin-top: 30px; }}
.particles {{ position: absolute; top:0; left:0; right:0; bottom:0; pointer-events:none; }}
.dot {{ position: absolute; border-radius: 50%; width: 3px; height: 3px; }}
.subtitle-overlay {{
  position: absolute; bottom: 50px; left: 0; right: 0;
  text-align: center; z-index: 100;
  font-family: 'Noto Sans SC', sans-serif;
  font-size: 32px; color: {sub_cfg.get("color", "#ffffff") if sub_cfg.get("enabled", False) else "transparent"};
  text-shadow: 0 2px 8px rgba(0,0,0,{sub_cfg.get("bg_opacity", 0.5) if sub_cfg.get("enabled", False) else "0"});
  pointer-events: none;
}}
  </style>
</head>
<body>

<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">

{scenes_html}{sub_html}</div>

<script>
  window.__timelines = window.__timelines || {{}};
  const tl = gsap.timeline({{ paused: true }});

{tl_js}
  // mulberry32 seeded PRNG
  function mulberry32(a) {{
    return function() {{
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    }};
  }}
  var rng = mulberry32(42);
  function mkParticles(id) {{
    const c = document.getElementById(id);
    if (!c) return;
    for (let i = 0; i < 10; i++) {{
      const d = document.createElement('div');
      d.className = 'dot';
      d.style.left = (rng() * 95) + '%';
      d.style.top = (rng() * 95) + '%';
      d.style.background = rng() > 0.5 ? '{particle_c1}' : '{particle_c2}';
      c.appendChild(d);
    }}
  }}
  for (let i = 1; i <= {n_scenes}; i++) mkParticles('p' + i);

  // 字幕显隐控制
  {'' if not sub_cfg.get("enabled", False) else '''
  const subElements = document.querySelectorAll('.subtitle-overlay');
  subElements.forEach(el => {
    const s = parseFloat(el.dataset.start) || 0;
    const d = parseFloat(el.dataset.duration) || 5;
    tl.set(el, {opacity: 0}, 0);
    tl.to(el, {opacity: 1, duration: 0.3}, s);
    tl.to(el, {opacity: 0, duration: 0.3}, s + d - 0.3);
  });
'''}

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

    voice = vo_cfg.get("voice", vo_cfg.get("default_voice", "zh-CN-XiaoxiaoNeural"))

    rate = vo_cfg.get("rate", "+0%")

    tts_output = template_dir / "voiceover.wav"
    if tts_output.exists():
        tts_output.unlink()

    # 使用edge-tts生成
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
        dur = get_audio_duration(voiceover_path) if voiceover_path else 18
        # BGM循环+音量调节
        audio_streams.append(f"[{input_idx}:a]volume={bgm_volume},aloop=loop=-1:size=0,atrim=duration={dur}[a{input_idx}]")
        input_idx += 1

    # 构建filter图
    if len(audio_streams) == 1:
        import re
        m = re.findall(r'\[([^\]]+)\]', audio_streams[0])
        out_label = f"[{m[-1]}]" if m else "[a1]"
        mix_filter = audio_streams[0]
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
