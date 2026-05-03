"""
素材管理模块 — 通用上传 + 背景图分类管理
"""
import json, os, logging, sqlite3, shutil, uuid, subprocess, time
from pathlib import Path
from flask import request, jsonify, send_from_directory
from datetime import datetime
from hyperframes_app import BASE_DIR, ASSETS_DIR, USERS_DB, logger

# ===================== 素材上传管理 =====================

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

def _register_upload_routes(app):
    """注册素材上传路由"""

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        """用户上传素材（视频/图片）"""
        if "file" not in request.files:
            return jsonify({"error": "未上传文件"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "文件名为空"}), 400

        # 文件大小限制：50MB
        file.seek(0, 2)  # seek to end
        file_size = file.tell()
        file.seek(0)  # reset
        if file_size > 50 * 1024 * 1024:
            return jsonify({"error": "文件大小超过50MB限制"}), 400

        # 安全的文件名：检查扩展名
        original_name = file.filename
        ext = os.path.splitext(original_name)[1].lower()
        allowed = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".gif"}
        if ext not in allowed:
            return jsonify({"error": f"不支持的文件格式: {ext}，支持: {', '.join(allowed)}"}), 400

        # 防止路径穿越攻击
        if "/" in original_name or "\\" in original_name:
            return jsonify({"error": "文件名不合法"}), 400

        safe_name = f"{uuid.uuid4()}{ext}"
        save_path = UPLOAD_DIR / safe_name
        file.save(str(save_path))
        size_mb = save_path.stat().st_size / (1024 * 1024)

        media_type = "video" if ext in {".mp4", ".mov", ".webm"} else "image"

        logger.info(f"素材上传: {file.filename} -> {safe_name} ({size_mb:.1f}MB, {media_type})")
        return jsonify({
            "success": True,
            "filename": safe_name,
            "original_name": file.filename,
            "size_mb": round(size_mb, 1),
            "type": media_type,
            "url": f"/uploads/{safe_name}"
        })

    @app.route("/api/uploads", methods=["GET"])
    def api_list_uploads():
        """获取已上传的素材列表"""
        files = []
        for f in sorted(UPLOAD_DIR.iterdir()):
            if f.is_file():
                ext = f.suffix.lower()
                if ext in {".mp4", ".mov", ".webm"}:
                    mtype = "video"
                elif ext in {".jpg", ".jpeg", ".png", ".gif"}:
                    mtype = "image"
                else:
                    continue
                files.append({
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    "type": mtype,
                    "url": f"/uploads/{f.name}",
                    "modified": f.stat().st_mtime
                })
        return jsonify({"files": sorted(files, key=lambda x: x["modified"], reverse=True)})

    @app.route("/api/upload/delete", methods=["POST"])
    def api_delete_upload():
        """删除上传的素材"""
        data = request.json or {}
        filename = data.get("filename", "")
        if not filename:
            return jsonify({"error": "缺少filename"}), 400
        # 防止路径穿越
        if "/" in filename or "\\" in filename or ".." in filename:
            return jsonify({"error": "文件名不合法"}), 400
        filepath = UPLOAD_DIR / filename
        if filepath.exists() and filepath.parent == UPLOAD_DIR:
            filepath.unlink()
            return jsonify({"success": True})
        return jsonify({"error": "文件不存在"}), 404

    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(str(UPLOAD_DIR), filename)


# ============================================================
# 背景图分类管理系统 API
# ============================================================
BG_UPLOAD_DIR = ASSETS_DIR

def _get_db():
    conn = sqlite3.connect(str(USERS_DB))
    conn.row_factory = sqlite3.Row
    return conn

def _register_bg_routes(app):
    """注册背景图管理路由"""
    BG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # --- 分类管理 ---

    @app.route("/api/bg/categories", methods=["GET"])
    def api_bg_categories():
        """获取所有分类"""
        conn = _get_db()
        rows = conn.execute("SELECT * FROM bg_categories ORDER BY sort_order ASC, id ASC").fetchall()
        conn.close()
        cats = []
        for r in rows:
            cats.append({
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "sort_order": r["sort_order"],
                "created_at": r["created_at"]
            })
        return jsonify({"categories": cats})

    @app.route("/api/bg/category/create", methods=["POST"])
    def api_bg_category_create():
        """创建分类"""
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "分类名不能为空"}), 400
        description = data.get("description", "").strip()
        conn = _get_db()
        try:
            now = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO bg_categories (name, description, sort_order, created_at) VALUES (?, ?, ?, ?)",
                (name, description, 0, now)
            )
            conn.commit()
            cat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return jsonify({"success": True, "id": cat_id, "name": name})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": f"分类 '{name}' 已存在"}), 400

    @app.route("/api/bg/category/rename", methods=["POST"])
    def api_bg_category_rename():
        """重命名分类"""
        data = request.json or {}
        cat_id = data.get("id")
        name = data.get("name", "").strip()
        if not cat_id or not name:
            return jsonify({"error": "缺少id或name"}), 400
        conn = _get_db()
        try:
            conn.execute("UPDATE bg_categories SET name = ? WHERE id = ?", (name, cat_id))
            conn.commit()
            conn.close()
            return jsonify({"success": True})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": f"分类名 '{name}' 已存在"}), 400

    @app.route("/api/bg/category/delete", methods=["POST"])
    def api_bg_category_delete():
        """删除分类（级联删除图片）"""
        data = request.json or {}
        cat_id = data.get("id")
        if not cat_id:
            return jsonify({"error": "缺少id"}), 400
        conn = _get_db()
        # 先删除图片文件
        rows = conn.execute("SELECT file_path, thumbnail_path FROM bg_images WHERE category_id = ?", (cat_id,)).fetchall()
        for r in rows:
            for p in [r["file_path"], r["thumbnail_path"]]:
                if p:
                    fp = Path(p)
                    if fp.exists():
                        fp.unlink()
        # 删除数据库记录（级联）
        conn.execute("DELETE FROM bg_categories WHERE id = ?", (cat_id,))
        conn.commit()
        conn.close()
        # 删除分类目录
        cat_dir = BG_UPLOAD_DIR / str(cat_id)
        if cat_dir.exists():
            shutil.rmtree(str(cat_dir), ignore_errors=True)
        return jsonify({"success": True})

    # --- 图片管理 ---

    @app.route("/api/bg/upload", methods=["POST"])
    def api_bg_upload():
        """上传图片到分类"""
        if "file" not in request.files:
            return jsonify({"error": "未上传文件"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "文件名为空"}), 400
        category_id = request.form.get("category_id", "")
        if not category_id:
            return jsonify({"error": "缺少category_id"}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"}
        if ext not in allowed:
            return jsonify({"error": f"不支持的文件格式: {ext}"}), 400

        # 文件大小限制 50MB
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > 50 * 1024 * 1024:
            return jsonify({"error": "文件大小超过50MB限制"}), 400

        safe_name = f"{uuid.uuid4()}{ext}"
        # 保存到分类目录
        cat_dir = BG_UPLOAD_DIR / str(category_id)
        cat_dir.mkdir(parents=True, exist_ok=True)
        save_path = cat_dir / safe_name
        file.save(str(save_path))

        # 生成缩略图（图片用PIL，视频用第一帧）
        thumb_name = f"thumb_{safe_name}"
        thumb_path = cat_dir / thumb_name
        thumb_url = ""
        is_video = ext in {".mp4", ".mov", ".webm"}
        try:
            if is_video:
                # 视频取第一帧
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(save_path),
                    "-vframes", "1", "-s", "320x568",
                    str(thumb_path)
                ], capture_output=True, text=True, timeout=30)
            else:
                # 图片用PIL生成缩略图
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(save_path)
                    img.thumbnail((320, 568))
                    img.save(str(thumb_path))
                except ImportError:
                    # 如果没有PIL，直接复制
                    shutil.copy2(str(save_path), str(thumb_path))
        except Exception as e:
            logger.warning(f"缩略图生成失败: {e}")

        if thumb_path.exists():
            thumb_url = f"/video-panel/uploads/bg/{category_id}/{thumb_name}"

        # 写入数据库
        conn = _get_db()
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO bg_images (category_id, file_path, file_name, thumbnail_path, duration, sort_order, file_size, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (category_id, str(save_path), file.filename, str(thumb_path), 4.0, 0, save_path.stat().st_size, now)
        )
        conn.commit()
        img_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        logger.info(f"背景图上传: category={category_id}, file={file.filename} -> {safe_name}")
        return jsonify({
            "success": True,
            "id": img_id,
            "url": f"/video-panel/uploads/bg/{category_id}/{safe_name}",
            "thumbnail_url": thumb_url,
            "file_name": file.filename,
            "file_size": save_path.stat().st_size
        })

    @app.route("/api/bg/list", methods=["GET"])
    def api_bg_list():
        """获取某分类下的所有图片"""
        category_id = request.args.get("category_id", "")
        if not category_id:
            return jsonify({"error": "缺少category_id"}), 400
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM bg_images WHERE category_id = ? ORDER BY sort_order ASC, id ASC",
            (category_id,)
        ).fetchall()
        conn.close()
        images = []
        prefix = "/video-panel"
        for r in rows:
            # 构建URL
            fp = Path(r["file_path"])
            rel = fp.relative_to(BASE_DIR) if fp.exists() else None
            url = f"{prefix}/{rel.as_posix()}" if rel else ""
            tp = Path(r["thumbnail_path"])
            thumb_rel = tp.relative_to(BASE_DIR) if tp.exists() else None
            thumb_url = f"{prefix}/{thumb_rel.as_posix()}" if thumb_rel else ""
            images.append({
                "id": r["id"],
                "category_id": r["category_id"],
                "url": url,
                "thumbnail_url": thumb_url,
                "file_name": r["file_name"],
                "duration": r["duration"],
                "sort_order": r["sort_order"],
                "file_size": r["file_size"],
                "created_at": r["created_at"]
            })
        return jsonify({"images": images})

    @app.route("/api/bg/reorder", methods=["POST"])
    def api_bg_reorder():
        """批量调整顺序"""
        data = request.json or {}
        items = data.get("images", [])
        if not items:
            return jsonify({"error": "缺少images"}), 400
        conn = _get_db()
        for item in items:
            img_id = item.get("id")
            sort_order = item.get("sort_order", 0)
            if img_id:
                conn.execute("UPDATE bg_images SET sort_order = ? WHERE id = ?", (sort_order, img_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    @app.route("/api/bg/duration", methods=["POST"])
    def api_bg_duration():
        """设置单张图片时长"""
        data = request.json or {}
        img_id = data.get("id")
        duration = data.get("duration", 4.0)
        if not img_id:
            return jsonify({"error": "缺少id"}), 400
        duration = max(0.5, min(30.0, float(duration)))
        conn = _get_db()
        conn.execute("UPDATE bg_images SET duration = ? WHERE id = ?", (duration, img_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    @app.route("/api/bg/delete", methods=["POST"])
    def api_bg_delete():
        """删除图片"""
        data = request.json or {}
        img_id = data.get("id")
        if not img_id:
            return jsonify({"error": "缺少id"}), 400
        conn = _get_db()
        row = conn.execute("SELECT file_path, thumbnail_path FROM bg_images WHERE id = ?", (img_id,)).fetchone()
        if row:
            for p in [row["file_path"], row["thumbnail_path"]]:
                if p:
                    fp = Path(p)
                    if fp.exists():
                        fp.unlink()
            conn.execute("DELETE FROM bg_images WHERE id = ?", (img_id,))
            conn.commit()
        conn.close()
        return jsonify({"success": True})

    # 提供背景图静态文件访问
    @app.route("/uploads/bg/<path:filename>")
    def serve_bg_upload(filename):
        return send_from_directory(str(BG_UPLOAD_DIR), filename)


def init_routes(app):
    """
    主入口：注册所有素材管理路由
    调用方式: init_routes(app)
    """
    _register_upload_routes(app)
    _register_bg_routes(app)
