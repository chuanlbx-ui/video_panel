#!/usr/bin/env python3
"""生成心学金句水印PNG + FFmpeg叠加脚本"""
import subprocess, os, sys
from pathlib import Path

# ===== 心学金句库 =====
QUOTES = [
    # 王阳明心学经典
    ("心即理", "心外无物，心外无理"),
    ("致良知", "知善知恶是良知"),
    ("知行合一", "知而不行，只是未知"),
    ("心即理", "此心光明，亦复何言"),
    ("致良知", "人人自有定盘针"),
    ("知行合一", "事上磨练，方立得住"),
    ("心即理", "破山中贼易，破心中贼难"),
    ("致良知", "减得一分人欲，便复得一分天理"),
    ("知行合一", "未有知而不行者，知而不行只是未知"),
    ("心即理", "你未看此花时，此花与汝心同归于寂"),
    
    # 协会品牌
    ("滇边AI", "心学智造 · 知行合一"),
    ("文山州互联网协会", "从投资物到投资人"),
    ("滇边AI", "AI数字工匠 · 致良知"),
]

def pick_quote(index=0):
    """根据索引循环选金句"""
    q = QUOTES[index % len(QUOTES)]
    return q[0], q[1]

def generate_watermark_png(output_path: str, index: int = 0, width: int = 1080, height: int = 1920):
    """用Pillow生成心学金句PNG水印"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # 尝试安装
        subprocess.run([sys.executable, "-m", "pip", "install", "pillow", "-q"], 
                      capture_output=True)
        from PIL import Image, ImageDraw, ImageFont
    
    title, body = pick_quote(index)
    
    # 半透明底图（全透明，只有文字）
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 找中文字体
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break
    
    if not font_path:
        # 尝试找任何可用的中文字体
        import glob
        candidates = glob.glob("/usr/share/fonts/**/*.ttc", recursive=True) + \
                     glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
        # 过滤中文字体
        for c in candidates:
            if any(kw in c.lower() for kw in ['noto', 'cjk', 'wqy', 'droid', 'chinese', 'cn']):
                font_path = c
                break
        if not font_path and candidates:
            font_path = candidates[0]  # 兜底
    
    # 底部水印位置（右下角区域）
    try:
        if font_path:
            font_title = ImageFont.truetype(font_path, 38)
            font_body = ImageFont.truetype(font_path, 30)
        else:
            font_title = ImageFont.load_default()
            font_body = ImageFont.load_default()
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
    
    # 画水印：底部深色渐变条背景
    bar_h = 110
    bar_y = height - bar_h - 30
    for y in range(bar_y, height):
        alpha = int(160 * (1 - (y - bar_y) / bar_h))
        if alpha > 0:
            draw.rectangle([0, y, width, y+1], fill=(6, 14, 30, min(alpha, 180)))
    
    # 金色装饰线
    gold_bar_y = bar_y + 18
    draw.rectangle([width - 420, gold_bar_y, width - 30, gold_bar_y + 4], fill=(255, 213, 79, 220))
    
    # 文字（加大、加亮，右下角对齐）
    title_text = f"✦ {title}"
    body_text = f"「{body}」"
    
    # 右下角对齐
    title_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    body_bbox = draw.textbbox((0, 0), body_text, font=font_body)
    title_w = title_bbox[2] - title_bbox[0]
    body_w = body_bbox[2] - body_bbox[0]
    max_w = max(title_w, body_w)
    
    tx = width - 30 - max_w
    draw.text((tx, gold_bar_y + 14), title_text, fill=(255, 213, 79, 230), font=font_title)
    
    bx = width - 30 - max_w
    draw.text((bx, gold_bar_y + 14 + 48), body_text, fill=(255, 255, 255, 180), font=font_body)
    
    img.save(output_path, "PNG")
    return output_path


def overlay_watermark(video_path: str, watermark_png: str, output_path: str, position: str = "overlay"):
    """用FFmpeg叠加水印到视频"""
    # position: overlay=右下角, overlay=W-w-40: H-h-40 (右下留边40px)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", watermark_png,
        "-filter_complex", "[0:v][1:v]overlay=W-w-40:H-h-40",
        "-c:a", "copy",
        output_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"水印叠加失败: {r.stderr[:300]}")
    return output_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/test_watermark.png")
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("video", nargs="?")
    args = parser.parse_args()
    
    png = generate_watermark_png(args.output, args.index)
    print(f"水印已生成: {png}")
    
    if args.video:
        out = args.video.replace(".mp4", "_watermarked.mp4")
        overlay_watermark(args.video, png, out)
        print(f"水印叠加完成: {out}")
