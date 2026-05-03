#!/usr/bin/env python3
"""
将 template_config.json 转换为 hyperframes index.html + TTS配音 + BGM合成

AI日报竖版短视频（1080×1920），科技蓝风格，5场景简化版。

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

    colors_scheme = cfg.get("colors", {}).get("scheme", "tech_blue")
    colors_opts = cfg.get("colors", {}).get("options", [])
    cs = colors_opts[0] if colors_opts else {"bg_top": "#0a1628", "bg_bottom": "#0d1f3c",
                                               "white_text": "#fff", "gold_text": "#64b5f6",
                                               "cyan_text": "#00d4ff", "subtitle_color": "rgba(100,181,246,0.4)"}
    for opt in colors_opts:
        if opt["id"] == colors_scheme:
            cs = opt
            break

    anim_style = cfg.get("animation", {}).get("style", "slide")

    # 特效参数
    effects = cfg.get("effects", {})
    transition_style = effects.get("transition_style", "fade")
    particle_density = effects.get("particle_density", "medium")
    glow_enabled = effects.get("glow_enabled", False)

    bg_top, bg_bottom = cs["bg_top"], cs["bg_bottom"]
    col_white, col_gold, col_cyan = cs["white_text"], cs["gold_text"], cs["cyan_text"]
    col_sub = cs["subtitle_color"]

    # 场景渐变（AI日报快节奏风格）
    gradient_s1 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 40%, {darken(bg_top)} 100%)"
    gradient_s2 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 30%, {bg_top} 100%)"
    gradient_s3 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 30%, {bg_top} 100%)"
    gradient_s4 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 30%, {bg_top} 100%)"
    gradient_s5 = f"radial-gradient(ellipse at center, {bg_top} 0%, {bg_bottom} 50%, {darken(bg_top)} 100%)"

    particle_c1 = f"rgba({hex_to_rgb_str(col_gold)},0.12)"
    particle_c2 = f"rgba({hex_to_rgb_str(col_cyan)},0.10)"

    # 粒子数量按密度调整（日报场景少粒子更干净）
    particle_count_map = {"low": 6, "medium": 12, "high": 20}
    n_particles = particle_count_map.get(particle_density, 12)

    # 转场CSS
    transition_class = ""
    if transition_style == "fade":
        transition_class = "transition: opacity 0.4s ease;"
    elif transition_style == "slide":
        transition_class = "transition: transform 0.5s ease, opacity 0.5s ease;"
    elif transition_style == "zoom":
        transition_class = "transition: transform 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94), opacity 0.5s ease;"

    # 辉光效果
    glow_css = ""
    if glow_enabled:
        glow_css = """
.scene::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(ellipse at 50% 30%, rgba(100,181,246,0.03) 0%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}"""

    gradients = [gradient_s1, gradient_s2, gradient_s3, gradient_s4, gradient_s5]

    scenes_html = ""
    tl_lines = []

    for idx, sc in enumerate(scenes):
        elems_html = ""
        for key, val in sc.get("elements", {}).items():
            st = val.get("style", "")
            tx = val.get("text", "")
            elems_html += f'    <div class="{st}" id="{sc["id"]}_{key}">{tx}</div>\n'

        gradient_style = gradients[idx] if idx < len(gradients) else gradient_s1
        scenes_html += (
            f'  <!-- ===== {sc["name"]} ({sc["start"]}-{sc["start"]+sc["duration"]}s) ===== -->\n'
            f'  <div id="{sc["id"]}" class="scene" data-start="{sc["start"]}" data-duration="{sc["duration"]}" style="background:{gradient_style}">\n'
            f'    <div class="particles" id="p{idx+1}"></div>\n'
            f'{elems_html}  </div>\n\n'
        )

        t = sc["start"]
        for key in sc.get("elements", {}):
            eid = f'"{sc["id"]}_{key}"'
            if anim_style == "scale":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,scale:0.5,duration:0.4,ease:"back.out(1.7)"}},{t});')
            elif anim_style == "glitch":
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,x:-10,duration:0.12}},{t});')
                tl_lines.append(f'  tl.to({eid}, {{opacity:1,x:0,duration:0.08}},{t}+0.12);')
            elif anim_style == "slide":
                side = "x:-60" if idx % 2 == 0 else "x:60"
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,{side},duration:0.4,ease:"power2.out"}},{t});')
            else:
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,y:40,duration:0.4}},{t});')
            t += 0.4

    tl_js = "\n".join(tl_lines)
    dur = cfg["settings"].get("video_duration", 25)
    n_scenes = len(scenes)

    html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={w}, height={h}" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@500;700;900&display=swap" rel="stylesheet">
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
#s4 {{ background: {gradient_s4}; }}
#s5 {{ background: {gradient_s5}; }}

.icon {{ font-size: 80px; margin-bottom: 20px; }}
.large_white {{ font-weight: 900; font-size: 110px; color: {col_white}; text-shadow: 0 0 40px rgba(100,180,255,0.3); }}
.large_gold {{ font-weight: 900; font-size: 110px; color: {col_gold}; text-shadow: 0 0 40px rgba(100,181,246,0.3); }}
.large_cyan {{ font-weight: 900; font-size: 100px; color: {col_cyan}; text-shadow: 0 0 40px rgba(0,212,255,0.3); }}
.subtitle {{ font-weight: 500; font-size: 36px; color: {col_sub}; margin-top: 30px; letter-spacing: 4px; }}
.tag {{ font-weight: 700; font-size: 32px; color: {col_cyan}; margin-bottom: 20px; letter-spacing: 3px; }}
.info {{ font-family: 'Noto Sans SC', sans-serif; font-weight: 500; font-size: 40px; color: {col_sub}; text-align: center; line-height: 1.6; margin-top: 20px; }}
.particles {{ position: absolute; top:0; left:0; right:0; bottom:0; pointer-events:none; }}
.dot {{ position: absolute; border-radius: 50%; width: 2px; height: 2px; }}
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


def main():
    build_from_config_main(build_html, script_path=__file__)


if __name__ == "__main__":
    main()
