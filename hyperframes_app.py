#!/usr/bin/env python3
"""
hyperframes Web面板 — Flask后端 V3 （精简主入口）
多模板系统 + 动态背景 + 字幕 + 批量生成
各功能模块已拆分到 api_templates, api_video, api_user, api_admin, api_bg, api_wechat
"""
import json, os, sys, uuid, subprocess, threading, smtplib, shutil, logging, hashlib, time, sqlite3, secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from functools import wraps
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ===================== 全局变量 =====================
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
JOBS = {}             # 单个作业
BATCH_QUEUE = []      # 批量作业队列
JOBS_FILE = BASE_DIR / "jobs.json"
JOBS_LOCK = threading.Lock()
STATS_LOCK = threading.Lock()
JOBS_DB_LOCK = threading.Lock()
ASSETS_DIR = BASE_DIR / "assets"
BG_LOOPS_DIR = ASSETS_DIR / "bg_loops"
USERS_DB = BASE_DIR / "users.db"

# 用户系统常量
USAGE_STATS = {
    "total_generates": 0,
    "by_template": {},
    "by_result": {"completed": 0, "failed": 0, "queued": 0},
    "daily": {},
    "invites_sent": 0,
    "invite_conversions": 0,
}
ROLE_HIERARCHY = {'admin': 3, 'vip': 2, 'user': 1}
FREE_DAILY_LIMIT = 5
VIP_DAILY_LIMIT = 100
INVITE_LINK_BASE = "ws.aiedu.yn.cn"

# ===================== 循环队列清理器 =====================
def cleanup_stale_jobs():
    """清理超时作业"""
    now = time.time()
    stale = [jid for jid, j in JOBS.items()
             if j.get("_created", now) and now - j.get("_created", now) > 3600
             and j.get("status") in ("rendering", "queued")]
    for jid in stale:
        JOBS[jid]["status"] = "failed"
        JOBS[jid]["error"] = "渲染超时"

def _stale_job_cleaner_loop():
    while True:
        time.sleep(300)
        cleanup_stale_jobs()

def _queue_timeout_check_loop():
    """队列超时检查"""
    while True:
        time.sleep(60)
        with STATS_LOCK:
            pass

# ===== 数据统计 =====
def record_usage(template_id: str, result: str):
    """记录使用统计到SQLite"""
    import sqlite3
    db = BASE_DIR / "stats.db"
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        conn.execute("CREATE TABLE IF NOT EXISTS usage_log(id INTEGER PRIMARY KEY AUTOINCREMENT, template_id TEXT, result TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO usage_log(template_id, result) VALUES (?, ?)", (template_id, result))
        conn.commit()
        conn.close()
    except Exception:
        pass

def record_user_video(job_id: str):
    """将完成的视频关联到用户"""
    try:
        job = JOBS.get(job_id)
        if not job:
            return
        user_phone = job.get("user_phone", "")
        if not user_phone:
            return
        import sqlite3
        conn = sqlite3.connect(str(USERS_DB), timeout=5)
        conn.execute("""
            INSERT OR IGNORE INTO user_videos (job_id, user_phone, template_id, created_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, user_phone, job.get("template_id", ""),
              datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ===================== 持久化 =====================
def jobs_load_all():
    """从jobs.json加载历史作业"""
    if JOBS_FILE.exists():
        try:
            with open(JOBS_FILE) as f:
                data = json.load(f)
                JOBS.update(data)
        except Exception:
            pass

def jobs_save(job_id, data=None):
    """保存单个作业到持久化文件"""
    with JOBS_LOCK:
        try:
            existing = {}
            if JOBS_FILE.exists():
                with open(JOBS_FILE) as f:
                    existing = json.load(f)
            if data:
                existing[job_id] = data
            else:
                existing[job_id] = JOBS.get(job_id, {})
            with open(JOBS_FILE, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def jobs_delete(job_id):
    """删除作业记录"""
    with JOBS_LOCK:
        try:
            existing = {}
            if JOBS_FILE.exists():
                with open(JOBS_FILE) as f:
                    existing = json.load(f)
            existing.pop(job_id, None)
            with open(JOBS_FILE, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def jobs_update_status(job_id, status, **kwargs):
    """更新作业状态并持久化"""
    if job_id in JOBS:
        JOBS[job_id]["status"] = status
        for k, v in kwargs.items():
            JOBS[job_id][k] = v
        jobs_save(job_id)

# ===================== Flask应用初始化 =====================
app = Flask(__name__)
app.secret_key = "hyperframes_secret_key_2024"

# 加载历史作业
jobs_load_all()

# 启动后台线程
t_cleaner = threading.Thread(target=_stale_job_cleaner_loop, daemon=True)
t_cleaner.start()
t_queue = threading.Thread(target=_queue_timeout_check_loop, daemon=True)
t_queue.start()

# ===================== 注册各功能模块 =====================
from api_templates import init_routes as init_template_routes
from api_video import init_routes as init_video_routes
from api_user import init_routes as init_user_routes
from api_admin import init_routes as init_admin_routes
from api_bg import init_routes as init_bg_routes
from api_wechat import init_routes as init_wechat_routes

init_template_routes(app)
init_video_routes(app)
init_user_routes(app)
init_admin_routes(app)
init_bg_routes(app)
init_wechat_routes(app)


@app.route("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("视频配置面板 V3 启动（模块化版）")
    logger.info(f"  Port: 8766")
    logger.info(f"  模板: {BASE_DIR}")
    logger.info(f"  背景: {BG_LOOPS_DIR}")
    logger.info(f"  输出: {OUTPUT_DIR}")
    logger.info("  6个功能模块已加载")
    logger.info("=" * 50)
    app.run(host="0.0.0.0", port=8766, debug=False)
