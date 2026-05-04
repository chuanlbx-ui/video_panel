#!/usr/bin/env python3
"""
磁盘清理脚本：清理旧的 work 目录、重复 BGM 文件、旧缓存等
"""
import os, shutil, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NOW = time.time()
FREED = 0

def log_freed(path, size):
    global FREED
    mb = size / (1024 * 1024)
    FREED += mb
    print(f"  释放 {mb:.1f}MB: {path}")

# 1. 清理旧的 work-* 目录（超过24小时）
print("=== 清理 work-* 目录 ===")
for subdir in BASE_DIR.iterdir():
    if subdir.is_dir() and subdir.name.startswith("work-"):
        age = NOW - subdir.stat().st_mtime
        if age > 86400:  # 24小时
            size = sum(f.stat().st_size for f in subdir.rglob("*") if f.is_file())
            log_freed(subdir, size)
            shutil.rmtree(subdir, ignore_errors=True)

# 也在模板子目录中查找
for template_dir in BASE_DIR.iterdir():
    if template_dir.is_dir() and (template_dir / "template_config.json").exists():
        for subdir in template_dir.iterdir():
            if subdir.is_dir() and subdir.name.startswith("work-"):
                age = NOW - subdir.stat().st_mtime
                if age > 86400:
                    size = sum(f.stat().st_size for f in subdir.rglob("*") if f.is_file())
                    log_freed(subdir, size)
                    shutil.rmtree(subdir, ignore_errors=True)

# 2. 清理旧缓存（output/cache_*.mp4 超过7天）
print("\n=== 清理过期缓存 ===")
output_dir = BASE_DIR / "output"
if output_dir.exists():
    for f in output_dir.glob("cache_*.mp4"):
        age = NOW - f.stat().st_mtime
        if age > 7 * 86400:
            log_freed(f, f.stat().st_size)
            f.unlink()

# 3. 清理旧的 output_*.mp4 文件（除了最近50个）
print("\n=== 清理旧输出文件 ===")
if output_dir.exists():
    mp4s = sorted(output_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in mp4s[50:]:  # 保留最近50个
        if f.name.startswith("cache_"):
            continue  # 缓存文件上面已经处理了
        if f.name == "output.mp4":
            continue  # 保留默认输出
        log_freed(f, f.stat().st_size)
        f.unlink()

# 4. 清理模板目录中不再是当前版本的 output_final.mp4 / raw_output.mp4
print("\n=== 清理模板目录中的残留视频 ===")
for template_dir in BASE_DIR.iterdir():
    if template_dir.is_dir() and (template_dir / "template_config.json").exists():
        for fname in ["output_final.mp4", "raw_output.mp4"]:
            fp = template_dir / fname
            if fp.exists():
                age = NOW - fp.stat().st_mtime
                if age > 3600:  # 超过1小时
                    log_freed(fp, fp.stat().st_size)
                    fp.unlink()

print(f"\n总计释放: {FREED:.1f}MB")
