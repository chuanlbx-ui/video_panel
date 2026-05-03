# ============================================================
# api_user.py — 用户/登录/权限模块
# ============================================================
import sqlite3, secrets, hashlib, json, logging, os
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify
from hyperframes_app import USERS_DB, ROLE_HIERARCHY, FREE_DAILY_LIMIT, VIP_DAILY_LIMIT, INVITE_LINK_BASE, JOBS, BASE_DIR, STATS_LOCK, USAGE_STATS

logger = logging.getLogger(__name__)


# ===== 数据库初始化 =====
def _init_users_db():
    conn = sqlite3.connect(str(USERS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            token TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)
    conn.commit()
    # 迁移：添加邀请裂变字段（如已存在则忽略）
    for col in ("invited_by", "invite_code", "role", "api_key", "daily_usage", "daily_reset", "password"):
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass
    # 为现有字段设置默认值
    conn.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    conn.execute("UPDATE users SET daily_usage = 0 WHERE daily_usage IS NULL")

    # === 背景图分类管理系统 ===
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bg_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bg_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            file_path TEXT NOT NULL,
            file_name TEXT NOT NULL,
            thumbnail_path TEXT DEFAULT '',
            duration REAL DEFAULT 4.0,
            sort_order INTEGER DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES bg_categories(id) ON DELETE CASCADE
        )
    """)
    # 初始化默认分类
    cur = conn.execute("SELECT COUNT(*) FROM bg_categories")
    count = cur.fetchone()[0]
    if count == 0:
        now = datetime.now().isoformat()
        default_cats = [
            ("食品主题", "美食相关背景图片", 0),
            ("科技数码", "科技数码类背景图片", 1),
            ("文山风光", "文山本地风光背景图片", 2),
        ]
        for name, desc, sort in default_cats:
            try:
                conn.execute(
                    "INSERT INTO bg_categories (name, description, sort_order, created_at) VALUES (?, ?, ?, ?)",
                    (name, desc, sort, now)
                )
            except Exception:
                pass
        conn.commit()
    # 用户视频历史记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT NOT NULL,
            job_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            brand TEXT DEFAULT '',
            config_json TEXT DEFAULT '{}',
            file_path TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_phone) REFERENCES users(phone)
        )
    """)
    # === 作业持久化表 ===
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'queued',
            template_id TEXT DEFAULT '',
            config_json TEXT DEFAULT '{}',
            progress TEXT DEFAULT '',
            output TEXT DEFAULT '',
            error TEXT DEFAULT '',
            user_phone TEXT DEFAULT '',
            is_batch INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            template_path TEXT DEFAULT '',
            config_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'queued',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


# ===== API Key 生成 =====
def generate_api_key():
    return "hf_" + secrets.token_hex(32)


# ===== 角色装饰器 =====
def require_role(min_role='user'):
    """在 require_login 基础上检查角色。admin > vip > user"""
    min_level = ROLE_HIERARCHY.get(min_role, 1)
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # 先验证登录 / API Key
            token = None
            api_key = None
            auth = request.headers.get("Authorization")
            if auth:
                if auth.startswith("Bearer "):
                    token = auth[7:]
                elif auth.startswith("hf_"):
                    api_key = auth
            if not token:
                token = request.args.get("token")
            if not token and not api_key:
                api_key = request.headers.get("X-API-Key")

            conn = sqlite3.connect(str(USERS_DB))
            user = None
            if api_key:
                cur = conn.execute(
                    "SELECT phone, name, role FROM users WHERE api_key = ?",
                    (api_key,)
                )
                row = cur.fetchone()
                if row:
                    user = {"phone": row[0], "name": row[1], "role": row[2], "api_key_auth": True}
            elif token:
                cur = conn.execute(
                    "SELECT phone, name, role FROM users WHERE token = ?",
                    (token,)
                )
                row = cur.fetchone()
                if row:
                    user = {"phone": row[0], "name": row[1], "role": row[2], "api_key_auth": False}
            conn.close()

            if not user:
                return jsonify({"error": "未登录或API Key无效"}), 401

            user_level = ROLE_HIERARCHY.get(user["role"], 1)
            if user_level < min_level:
                return jsonify({"error": "权限不足"}), 403

            request.user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.args.get("token")
        if not token:
            return jsonify({"error": "未登录"}), 401
        conn = sqlite3.connect(str(USERS_DB))
        cur = conn.execute("SELECT phone, name FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "token无效"}), 401
        request.user = {"phone": row[0], "name": row[1]}
        return f(*args, **kwargs)
    return decorated


# ============================================================
# 路由注册
# ============================================================
def init_routes(app):

    @app.route("/api/apikey/generate", methods=["POST"])
    @require_role(min_role='user')
    def api_apikey_generate():
        """为当前用户生成新的API Key"""
        phone = request.user["phone"]
        new_key = generate_api_key()
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("UPDATE users SET api_key = ? WHERE phone = ?", (new_key, phone))
        conn.commit()
        conn.close()
        return jsonify({"api_key": new_key, "message": "API Key已生成，请妥善保管"})

    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request.json or {}
        phone = data.get("phone", "").strip()
        password = data.get("password", "").strip()
        if not phone:
            return jsonify({"error": "请输入手机号"}), 400
        token = secrets.token_hex(32)
        now = datetime.now().isoformat()
        ref_code = data.get("ref", "").strip()
        conn = sqlite3.connect(str(USERS_DB))
        # 检查用户是否存在
        cur = conn.execute("SELECT name, password FROM users WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row:
            stored_name, stored_password = row[0], (row[1] or "")
            # 有密码验证
            if stored_password:
                if not password:
                    conn.close()
                    return jsonify({"error": "请输入密码"}), 400
                input_hash = hashlib.sha256(password.encode()).hexdigest()
                if input_hash != stored_password:
                    conn.close()
                    return jsonify({"error": "密码错误"}), 403
            else:
                # 无密码用户（旧版）：登录时密码必须为空或跳过验证
                pass
            # 更新 token
            conn.execute("UPDATE users SET token=?, last_login=? WHERE phone=?",
                         (token, now, phone))
            conn.commit()
            conn.close()
            return jsonify({"token": token, "name": stored_name})
        # 用户不存在 — 自动注册（旧版兼容：无密码时自动创建）
        if password:
            conn.close()
            return jsonify({"error": "用户不存在，请先注册"}), 404
        # 旧版兼容：无密码，直接用手机号自动创建
        name = data.get("name", "").strip() or "用户" + phone[-4:]
        invited_by = None
        if ref_code:
            cur = conn.execute("SELECT phone FROM users WHERE invite_code = ?", (ref_code,))
            row2 = cur.fetchone()
            if row2:
                invited_by = row2[0]
                with STATS_LOCK:
                    USAGE_STATS["invite_conversions"] += 1
        conn.execute("""INSERT INTO users (phone, name, token, created_at, last_login, invited_by)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET name=excluded.name, token=excluded.token, last_login=excluded.last_login
        """, (phone, name, token, now, now, invited_by))
        conn.commit()
        conn.close()
        return jsonify({"token": token, "name": name})

    @app.route("/api/register", methods=["POST"])
    def api_register():
        data = request.json or {}
        phone = data.get("phone", "").strip()
        name = data.get("name", "").strip()
        password = data.get("password", "").strip()
        if not phone:
            return jsonify({"error": "请输入手机号"}), 400
        if not name:
            return jsonify({"error": "请输入姓名"}), 400
        if not password or len(password) < 6:
            return jsonify({"error": "密码至少6位"}), 400
        conn = sqlite3.connect(str(USERS_DB))
        # 检查手机号是否重复
        cur = conn.execute("SELECT phone FROM users WHERE phone = ?", (phone,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "该手机号已注册，请直接登录"}), 409
        token = secrets.token_hex(32)
        now = datetime.now().isoformat()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        ref_code = data.get("ref", "").strip()
        invited_by = None
        if ref_code:
            cur = conn.execute("SELECT phone FROM users WHERE invite_code = ?", (ref_code,))
            row = cur.fetchone()
            if row:
                invited_by = row[0]
                with STATS_LOCK:
                    USAGE_STATS["invite_conversions"] += 1
        conn.execute("""INSERT INTO users (phone, name, token, password, created_at, last_login, invited_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (phone, name, token, password_hash, now, now, invited_by))
        conn.commit()
        conn.close()
        return jsonify({"token": token, "name": name})

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        data = request.json or {}
        token = data.get("token", "")
        if token:
            conn = sqlite3.connect(str(USERS_DB))
            conn.execute("UPDATE users SET token = NULL WHERE token = ?", (token,))
            conn.commit()
            conn.close()
        return jsonify({"status": "ok"})

    @app.route("/api/me")
    def api_me():
        token = None
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth[7:]
        if not token:
            token = request.args.get("token")
        if not token:
            return jsonify({"error": "未登录"}), 401
        conn = sqlite3.connect(str(USERS_DB))
        cur = conn.execute("SELECT phone, name FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "token无效"}), 401
        return jsonify({"phone": row[0], "name": row[1]})

    @app.route("/api/user/videos", methods=["GET"])
    @require_login
    def api_user_videos():
        """获取当前用户的所有视频记录，按创建时间倒序"""
        phone = request.user["phone"]
        try:
            conn = sqlite3.connect(str(USERS_DB))
            cur = conn.execute(
                """SELECT id, job_id, template_id, brand, file_size, created_at
                   FROM user_videos
                   WHERE user_phone = ?
                   ORDER BY created_at DESC""",
                (phone,)
            )
            rows = cur.fetchall()
            conn.close()
            videos = []
            for row in rows:
                vid_id, job_id, template_id, brand, file_size, created_at = row
                download_url = f"{request.host_url}video-panel/api/download/{job_id}"
                videos.append({
                    "id": vid_id,
                    "job_id": job_id,
                    "template_id": template_id,
                    "brand": brand or "",
                    "file_size": file_size or 0,
                    "created_at": created_at,
                    "download_url": download_url
                })
            logger.info(f"[api_user_videos] 用户 {phone} 查询到 {len(videos)} 条视频记录")
            return jsonify({"videos": videos, "total": len(videos)})
        except Exception as e:
            logger.error(f"[api_user_videos] 查询失败: {e}")
            return jsonify({"error": "查询失败", "videos": [], "total": 0})

    @app.route("/api/user/video/delete", methods=["POST"])
    @require_login
    def api_user_video_delete():
        """删除用户自己的视频记录（数据库 + 文件）"""
        phone = request.user["phone"]
        data = request.json or {}
        job_id = data.get("job_id", "")
        if not job_id:
            return jsonify({"error": "缺少 job_id"}), 400
        try:
            conn = sqlite3.connect(str(USERS_DB))
            # 只允许删除自己的视频
            cur = conn.execute(
                "SELECT file_path FROM user_videos WHERE job_id = ? AND user_phone = ?",
                (job_id, phone)
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return jsonify({"error": "视频记录不存在或无权删除"}), 404
            file_path = row[0]
            # 删除数据库记录
            conn.execute("DELETE FROM user_videos WHERE job_id = ? AND user_phone = ?", (job_id, phone))
            conn.commit()
            conn.close()
            # 删除文件
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[api_user_video_delete] 已删除文件: {file_path}")
            # 同时清理JOBS内存记录
            if job_id in JOBS:
                del JOBS[job_id]
            logger.info(f"[api_user_video_delete] 用户 {phone} 删除了视频 {job_id}")
            return jsonify({"status": "ok", "message": "视频已删除"})
        except Exception as e:
            logger.error(f"[api_user_video_delete] 删除失败: {e}")
            return jsonify({"error": "删除失败"}), 500

    @app.route("/api/invite-code", methods=["GET"])
    @require_login
    def api_invite_code():
        """获取当前用户的邀请码（12位hex），不存在则自动生成"""
        phone = request.user["phone"]
        conn = sqlite3.connect(str(USERS_DB))
        cur = conn.execute("SELECT invite_code FROM users WHERE phone = ?", (phone,))
        row = cur.fetchone()
        if row and row[0]:
            code = row[0]
        else:
            code = secrets.token_hex(6)
            conn.execute("UPDATE users SET invite_code = ? WHERE phone = ?", (code, phone))
            conn.commit()
        conn.close()
        return jsonify({"invite_code": code, "invite_url": f"{INVITE_LINK_BASE}?ref={code}"})

    @app.route("/api/referral/record", methods=["POST"])
    def api_referral_record():
        """记录一次邀请转化：接收 invite_code，验证存在，计数"""
        data = request.json or {}
        invite_code = data.get("invite_code", "").strip()
        if not invite_code:
            return jsonify({"error": "缺少 invite_code"}), 400
        conn = sqlite3.connect(str(USERS_DB))
        cur = conn.execute("SELECT phone FROM users WHERE invite_code = ?", (invite_code,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "邀请码无效"}), 404
        with STATS_LOCK:
            USAGE_STATS["invite_conversions"] += 1
        return jsonify({"success": True, "referrer": row[0]})

    @app.route("/api/referral/stats", methods=["GET"])
    def api_referral_stats():
        """获取邀请统计数据"""
        with STATS_LOCK:
            invites_sent = USAGE_STATS.get("invites_sent", 0)
            conversions = USAGE_STATS.get("invite_conversions", 0)
        return jsonify({"invites_sent": invites_sent, "invite_conversions": conversions})
