#!/usr/bin/env python3
"""
将 template_config.json 转换为 hyperframes index.html + TTS配音 + BGM合成
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

    cs = get_color_scheme(config)
    anim_style = cfg.get("animation", {}).get("style", "standard")
    bg_type = cfg.get("settings", {}).get("bg_type",
                     cfg.get("background", {}).get("type", "gradient"))
    sub_cfg = cfg.get("subtitles", {})

    bg_top, bg_bottom = cs["bg_top"], cs["bg_bottom"]
    col_white, col_gold, col_cyan = cs["white_text"], cs["gold_text"], cs["cyan_text"]
    col_sub = cs["subtitle_color"]

    gradient_s1 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 30%, {blend_color(bg_bottom, '#132a50')} 60%, {bg_top} 100%)"
    gradient_s2 = f"linear-gradient(170deg, {bg_top} 0%, {bg_bottom} 40%, {bg_top} 100%)"
    gradient_s3 = f"linear-gradient(170deg, {bg_top} 0%, {blend_color(bg_bottom, '#132a50')} 50%, {bg_top} 100%)"
    particle_c1 = f"rgba({hex_to_rgb_str(col_gold)},0.15)"
    particle_c2 = f"rgba({hex_to_rgb_str(col_cyan)},0.12)"

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
            f'{elems_html}  </div>\n\n'
        )

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
            else:
                tl_lines.append(f'  tl.from({eid}, {{opacity:0,y:60,duration:0.6}},{t});')
            t += 0.6

    tl_js = "\n".join(tl_lines)
    dur = cfg["settings"].get("video_duration", 25)
    n_scenes = len(scenes)

    sub_html = ""
    if sub_cfg.get("enabled", False):
        sub_font_size = sub_cfg.get("font_size", 36)
        sub_color = sub_cfg.get("color", "#ffffff")
        sub_bg_opacity = sub_cfg.get("bg_opacity", 0.6)
        for idx, sc in enumerate(scenes):
            sub_text = sc.get("narration", "") or sc.get("elements", {}).get("sub", {}).get("text", "")
            if sub_text:
                sub_html += f'    <div class="subtitle-overlay clip" id="sub_{sc["id"]}" data-start="{sc["start"]}" data-duration="{sc["duration"]}">{sub_text}</div>\n'

    html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={w}, height={h}" />
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@700;900&family=Noto+Serif+SC:wght@700;900&display=swap" rel="stylesheet">
  <style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
html,body {{ width:{w}px;height:{h}px;overflow:hidden;background:{bg_top};font-family:'Noto Sans SC',sans-serif; }}
.scene {{ position:absolute;top:0;left:0;width:{w}px;height:{h}px;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden; }}
#s1 {{ background:{gradient_s1}; }}
#s2 {{ background:{gradient_s2}; }}
#s3 {{ background:{gradient_s3}; }}
.large_white {{ font-weight:900;font-size:130px;color:{col_white};text-shadow:0 0 60px rgba(100,180,255,0.3); }}
.large_gold {{ font-weight:900;font-size:130px;color:{col_gold};text-shadow:0 0 50px rgba(255,215,0,0.3); }}
.large_cyan {{ font-weight:900;font-size:130px;color:{col_cyan};text-shadow:0 0 50px rgba(0,212,255,0.3); }}
.subtitle {{ font-weight:700;font-size:40px;color:{col_sub};margin-top:40px;letter-spacing:6px; }}
.tags {{ font-weight:900;font-size:72px;color:{col_gold};text-align:center;line-height:1.5;text-shadow:0 0 30px rgba(255,215,0,0.2); }}
.price {{ font-weight:900;font-size:110px;color:{col_gold};text-shadow:0 0 60px rgba(255,215,0,0.5); }}
.info {{ font-family:'Noto Sans SC',sans-serif;font-weight:700;font-size:44px;color:#fff;text-align:center;line-height:1.6;margin-top:30px; }}
.phone {{ font-weight:900;font-size:48px;color:{col_cyan};margin-top:40px;text-shadow:0 0 20px rgba(0,212,255,0.3); }}
.limit {{ font-weight:700;font-size:40px;color:{col_sub};margin-top:30px; }}
.bullet {{ font-weight:700;font-size:56px;color:{col_white};text-align:center;line-height:1.8;margin:10px 0; }}
.particles {{ position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none; }}
.dot {{ position:absolute;border-radius:50%;width:3px;height:3px; }}
.subtitle-overlay {{ position:absolute;bottom:60px;left:0;right:0;text-align:center;z-index:100;font-family:'Noto Sans SC',sans-serif;font-size:{sub_cfg.get("font_size",36)}px;color:{sub_cfg.get("color","#ffffff") if sub_cfg.get("enabled") else "transparent"};text-shadow:0 2px 8px rgba(0,0,0,{sub_cfg.get("bg_opacity",0.6) if sub_cfg.get("enabled") else "0"});pointer-events:none; }}
  </style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">
{scenes_html}{sub_html}</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{tl_js}
function mulberry32(a){{return function(){{a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;}}}}
var rng=mulberry32(42);
function mkParticles(id){{const c=document.getElementById(id);if(!c)return;for(let i=0;i<15;i++){{const d=document.createElement('div');d.className='dot';d.style.left=(rng()*95)+'%';d.style.top=(rng()*95)+'%';d.style.background=rng()>0.5?'{particle_c1}':'{particle_c2}';c.appendChild(d);}}}}
for(let i=1;i<={n_scenes};i++) mkParticles('p'+i);
{'' if not sub_cfg.get("enabled", False) else '''
const subElements=document.querySelectorAll('.subtitle-overlay');
subElements.forEach(el=>{{const s=parseFloat(el.dataset.start)||0;const d=parseFloat(el.dataset.duration)||5;tl.set(el,{{opacity:0}},0);tl.to(el,{{opacity:1,duration:0.3}},s);tl.to(el,{{opacity:0,duration:0.3}},s+d-0.3);}});
'''}
window.__timelines["main"]=tl;
</script>
</body>
</html>"""
    
    jitter_cfg = config.get("_jitter", {}).get("enabled", False)
    if jitter_cfg:
        html = apply_random_jitter(html, rnd_seed=config["_jitter"].get("job_seed", hash(str(config))),
            font_range=config["_jitter"].get("font_size_range", 2),
            margin_pct=config["_jitter"].get("margin_top_range_pct", 5.0),
            particle_min=config["_jitter"].get("particle_mult_min", 0.7),
            particle_max=config["_jitter"].get("particle_mult_max", 1.3))
    return html


if __name__ == "__main__":
    build_from_config_main(build_html, script_path=__file__)
