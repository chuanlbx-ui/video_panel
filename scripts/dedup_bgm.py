#!/usr/bin/env python3
"""
BGM文件去重：将各模板中的重复 BGM 文件替换为指向 assets/bgm/ 的符号链接
可以节省 ~100MB+ 磁盘空间
"""
import hashlib, os, shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ASSETS_BGM = BASE_DIR / "assets" / "bgm"
ASSETS_BGM.mkdir(parents=True, exist_ok=True)

# 1. 收集所有 BGM 文件
bgm_files = []
for template_dir in sorted(BASE_DIR.iterdir()):
    bgm_dir = template_dir / "bgm"
    if bgm_dir.exists():
        for f in bgm_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ('.mp3', '.wav', '.ogg', '.m4a'):
                bgm_files.append(f)

print(f"共发现 {len(bgm_files)} 个 BGM 文件")

# 2. 按内容哈希去重
by_hash = {}
for fp in bgm_files:
    # 跳过已存在的符号链接
    if fp.is_symlink():
        continue
    h = hashlib.md5(fp.read_bytes()).hexdigest()
    if h not in by_hash:
        by_hash[h] = fp
    else:
        # 重复文件：删除并替换为符号链接
        original = by_hash[h]
        # 确保 assets/bgm 中有源文件
        dest_name = f"{original.name}"
        dest = ASSETS_BGM / dest_name
        if not dest.exists():
            shutil.copy2(original, dest)
            print(f"  复制源文件到: {dest}")
        rel = os.path.relpath(dest, start=fp.parent)
        fp.unlink()
        fp.symlink_to(rel)
        print(f"  替换为链接: {fp} -> {rel}")

print("BGM 去重完成")
