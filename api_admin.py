#!/usr/bin/env python3
"""
管理后台模块 — 用户管理、API Key管理、模板编辑、用量统计、磁盘清理
使用 init_routes(app) 模式注册路由
"""
import json, logging, sqlite3, shutil, subprocess, sys, re, uuid
from datetime import datetime
from pathlib import Path
from flask import request, jsonify, send_from_directory
from hyperframes_app import BASE_DIR, USERS_DB, JOBS, OUTPUT_DIR, STATS_LOCK, USAGE_STATS
from api_templates import discover_templates, _get_template
from api_user import require_role

logger = logging.getLogger(__name__)


# ===================== 路由注册 =====================

def init_routes(app):
    """注册所有管理后台相关路由"""

    @app.route("/admin")
    def admin():
        return send_from_directory(str(BASE_DIR / "templates"), "admin.html")

    @app.route("/api/admin/users", methods=["GET"])
    @require_role(min_role='admin')
    def api_admin_users():
        """用户列表（分页、搜索）"""
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        search = request.args.get("search", "").strip()
        conn = sqlite3.connect(str(USERS_DB))
        conn.row_factory = sqlite3.Row

        if search:
            cur = conn.execute(
                "SELECT id, phone, name, role, api_key, daily_usage, daily_reset, created_at, last_login, invited_by, invite_code "
                "FROM users WHERE phone LIKE ? OR name LIKE ? ORDER BY id DESC",
                (f"%{search}%", f"%{search}%")
            )
        else:
            cur = conn.execute(
                "SELECT id, phone, name, role, api_key, daily_usage, daily_reset, created_at, last_login, invited_by, invite_code "
                "FROM users ORDER BY id DESC"
            )
        all_rows = cur.fetchall()
        total = len(all_rows)
        offset = (page - 1) * per_page
        rows = all_rows[offset:offset + per_page]
        users = []
        for r in rows:
            users.append({
                "id": r["id"],
                "phone": r["phone"],
                "name": r["name"],
                "role": r["role"] or "user",
                "has_api_key": bool(r["api_key"]),
                "api_key": r["api_key"][:12] + "..." if r["api_key"] else None,
                "daily_usage": int(r["daily_usage"]) if r["daily_usage"] else 0,
                "daily_reset": r["daily_reset"] or "",
                "created_at": r["created_at"] or "",
                "last_login": r["last_login"] or "",
                "invited_by": r["invited_by"] or "",
                "invite_code": r["invite_code"] or ""
            })
        conn.close()
        return jsonify({"users": users, "total": total, "page": page, "per_page": per_page})

    @app.route("/api/admin/user/role", methods=["POST"])
    @require_role(min_role='admin')
    def api_admin_user_role():
        """修改用户角色"""
        data = request.json or {}
        phone = data.get("phone", "").strip()
        new_role = data.get("role", "").strip()
        if not phone or new_role not in ("user", "vip", "admin"):
            return jsonify({"error": "参数无效"}), 400
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("UPDATE users SET role = ? WHERE phone = ?", (new_role, phone))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": f"用户 {phone} 角色已变更为 {new_role}"})

    @app.route("/api/admin/apikeys", methods=["GET"])
    @require_role(min_role='admin')
    def api_admin_apikeys():
        """所有API Key列表"""
        conn = sqlite3.connect(str(USERS_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT phone, name, role, api_key, daily_usage, daily_reset "
            "FROM users WHERE api_key IS NOT NULL AND api_key != '' ORDER BY id DESC"
        )
        rows = cur.fetchall()
        keys = []
        for r in rows:
            keys.append({
                "phone": r["phone"],
                "name": r["name"],
                "role": r["role"] or "user",
                "api_key": r["api_key"],
                "daily_usage": int(r["daily_usage"]) if r["daily_usage"] else 0,
                "daily_reset": r["daily_reset"] or ""
            })
        conn.close()
        return jsonify({"apikeys": keys, "total": len(keys)})

    @app.route("/api/admin/apikey/revoke", methods=["POST"])
    @require_role(min_role='admin')
    def api_admin_apikey_revoke():
        """吊销API Key"""
        data = request.json or {}
        phone = data.get("phone", "").strip()
        if not phone:
            return jsonify({"error": "缺少phone参数"}), 400
        conn = sqlite3.connect(str(USERS_DB))
        conn.execute("UPDATE users SET api_key = NULL WHERE phone = ?", (phone,))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": f"用户 {phone} 的API Key已吊销"})

    @app.route("/api/admin/template/create", methods=["POST"])
    @require_role(min_role='admin')
    def api_admin_template_create():
        """创建新模板（带克隆功能，管理员专用）"""
        data = request.json or {}
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        clone_from = data.get("clone_from", "").strip()

        if not name:
            return jsonify({"error": "缺少模板名称"}), 400

        # 生成唯一 template_id
        safe_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '_', name)[:20]
        template_id = f"tpl_{safe_name}_{uuid.uuid4().hex[:4]}"

        # 检查ID是否冲突
        existing = _get_template(template_id)
        if existing:
            return jsonify({"error": "模板ID冲突，请重试"}), 500

        new_dir = BASE_DIR / template_id
        if new_dir.exists():
            return jsonify({"error": f"目录 '{template_id}' 已存在"}), 400

        try:
            new_dir.mkdir(parents=True, exist_ok=False)

            if clone_from:
                source_tpl = _get_template(clone_from)
                if not source_tpl:
                    shutil.rmtree(new_dir, ignore_errors=True)
                    return jsonify({"error": f"源模板 {clone_from} 不存在"}), 404

                # 深拷贝配置
                src_config = source_tpl["config"]
                new_config = json.loads(json.dumps(src_config))
                new_config["template_id"] = template_id
                new_config["template_name"] = name
                new_config["source"] = "custom"
                if description:
                    new_config["description"] = description

                # 复制其他文件
                source_path = Path(source_tpl["path"])
                for f in source_path.iterdir():
                    if f.is_file() and f.name != "template_config.json":
                        try:
                            shutil.copy(str(f), str(new_dir / f.name))
                        except Exception:
                            pass
            else:
                # 最小模板
                new_config = {
                    "template_id": template_id,
                    "template_name": name,
                    "version": "1.0",
                    "description": description or "",
                    "source": "custom",
                    "settings": {
                        "fps": 30,
                        "output_width": 1080,
                        "output_height": 1920,
                        "quality": "standard",
                        "video_bitrate": "15M",
                        "pixel_format": "yuv420p"
                    },
                    "audio": {
                        "bgm": {"enabled": True, "file": "", "volume": 0.12, "options": []},
                        "voiceover": {
                            "enabled": True,
                            "default_voice": "zh-CN-YunyangNeural",
                            "text": "",
                            "speed": 1.0
                        }
                    },
                    "colors": {
                        "scheme": "warm_dark",
                        "options": []
                    },
                    "background": {"type": "gradient", "options": []},
                    "animation": {"style": "standard", "options": []},
                    "effects": {
                        "transition_style": "fade",
                        "particle_density": "medium",
                        "glow_enabled": False
                    },
                    "scenes": [
                        {
                            "id": "s1",
                            "name": "开场",
                            "duration": 4,
                            "start": 0,
                            "elements": {
                                "line1": {"text": "标题文字", "style": "large_gold"},
                                "sub": {"text": "副标题", "style": "subtitle"}
                            }
                        }
                    ]
                }

            # 写入配置
            config_path = new_dir / "template_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)

            # 如果目录下没有build_from_config.py，从food_promo复制一个
            build_script = new_dir / "build_from_config.py"
            if not build_script.exists():
                default_build = BASE_DIR / "food_promo" / "build_from_config.py"
                if default_build.exists():
                    shutil.copy(str(default_build), str(build_script))

            logger.info(f"[Admin] 新模板已创建: {template_id} (名称: {name}, 克隆自: {clone_from or '无'})")
            return jsonify({
                "success": True,
                "template_id": template_id,
                "name": name,
                "message": f"模板 '{name}' 创建成功"
            })

        except Exception as e:
            shutil.rmtree(new_dir, ignore_errors=True)
            logger.error(f"[Admin] 创建模板失败: {e}")
            return jsonify({"error": f"创建失败: {str(e)}"}), 500

    @app.route("/api/admin/template/delete", methods=["POST"])
    @require_role(min_role='admin')
    def api_admin_template_delete():
        """删除模板（管理员专用）"""
        data = request.json or {}
        template_id = data.get("template_id", "").strip()
        if not template_id:
            return jsonify({"error": "缺少 template_id"}), 400

        tpl = _get_template(template_id)
        if not tpl:
            return jsonify({"error": "模板不存在"}), 404

        try:
            tpl_path = Path(tpl["path"])
            shutil.rmtree(str(tpl_path), ignore_errors=True)
            logger.info(f"[Admin] 模板已删除: {template_id}")
            return jsonify({"success": True, "message": f"模板 '{template_id}' 已删除"})
        except Exception as e:
            logger.error(f"[Admin] 删除模板失败: {e}")
            return jsonify({"error": f"删除失败: {str(e)}"}), 500

    @app.route("/api/admin/templates", methods=["GET"])
    @require_role(min_role='admin')
    def api_admin_templates():
        """获取所有模板的简化列表（用于管理后台）"""
        templates = discover_templates()
        result = []
        for t in templates:
            cfg = t.get("config", {})
            scenes = cfg.get("scenes", [])
            bg = cfg.get("background", {})
            has_bg_image = bg.get("type") == "video_loop"
            result.append({
                "id": t["id"],
                "name": cfg.get("template_name", t["id"]),
                "description": cfg.get("description", ""),
                "scenes_count": len(scenes),
                "has_bg_image": has_bg_image,
                "updated_at": "",
                "config_preview": {
                    "colors": cfg.get("colors", {}).get("scheme", ""),
                    "effects": cfg.get("effects", {}),
                    "audio": {
                        "bgm_enabled": cfg.get("audio", {}).get("bgm", {}).get("enabled", False),
                        "voiceover_enabled": cfg.get("audio", {}).get("voiceover", {}).get("enabled", False)
                    }
                }
            })
        return jsonify({"templates": result})

    @app.route("/api/admin/template-scenes/<template_id>", methods=["GET"])
    @require_role(min_role='admin')
    def api_admin_template_scenes(template_id):
        """获取模板的场景结构信息，用于管理后台编辑"""
        template = _get_template(template_id)
        if not template:
            return jsonify({"error": "模板未找到"}), 404

        cfg = template["config"]
        scenes = cfg.get("scenes", [])

        # 提取每个场景的可编辑字段
        scene_list = []
        for sc in scenes:
            elements = sc.get("elements", {})
            editable_elements = {}
            for key, el in elements.items():
                editable_elements[key] = {
                    "text": el.get("text", ""),
                    "style": el.get("style", ""),
                    "font_size": el.get("font_size", None),
                    "color": el.get("color", None),
                    "animation": el.get("animation", None)
                }
            scene_list.append({
                "id": sc["id"],
                "name": sc.get("name", f"场景 {sc['id']}"),
                "start": sc.get("start", 0),
                "duration": sc.get("duration", 4),
                "elements": editable_elements
            })

        # 配色方案选项
        color_options = cfg.get("colors", {}).get("options", [])

        # 音频设置
        audio = cfg.get("audio", {})
        bgm = audio.get("bgm", {})
        voiceover = audio.get("voiceover", {})

        # 效果设置
        effects = cfg.get("effects", {})

        # 动画设置
        animation = cfg.get("animation", {})

        result = {
            "template_id": template_id,
            "template_name": cfg.get("template_name", template_id),
            "description": cfg.get("description", ""),
            "colors": {
                "scheme": cfg.get("colors", {}).get("scheme", ""),
                "options": color_options
            },
            "audio": {
                "bgm": {
                    "enabled": bgm.get("enabled", False),
                    "volume": bgm.get("volume", 0.12),
                    "file": bgm.get("file", ""),
                    "options": bgm.get("options", [])
                },
                "voiceover": {
                    "enabled": voiceover.get("enabled", False),
                    "text": voiceover.get("text", ""),
                    "voice": voiceover.get("default_voice", ""),
                    "options": voiceover.get("options", []),
                    "speed": voiceover.get("speed", 1.0)
                }
            },
            "effects": {
                "transition_style": effects.get("transition_style", "fade"),
                "particle_density": effects.get("particle_density", "medium"),
                "glow_enabled": effects.get("glow_enabled", False),
                "options": effects.get("options", []),
                "density_options": effects.get("density_options", [])
            },
            "animation": {
                "style": animation.get("style", "standard"),
                "options": animation.get("options", [])
            },
            "scenes": scene_list,
            "full_config": cfg  # 包含完整的原始配置
        }

        return jsonify(result)

    @app.route("/api/admin/usage", methods=["GET"])
    @require_role(min_role='admin')
    def api_admin_usage():
        """用量统计日报"""
        conn = sqlite3.connect(str(USERS_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT phone, name, role, daily_usage, daily_reset FROM users ORDER BY daily_usage DESC"
        )
        rows = cur.fetchall()
        today = datetime.now().strftime("%Y-%m-%d")
        user_usages = []
        total_daily = 0
        active_today = 0
        for r in rows:
            usage = int(r["daily_usage"]) if r["daily_usage"] else 0
            reset_date = r["daily_reset"] or ""
            if reset_date == today:
                total_daily += usage
                active_today += 1
            user_usages.append({
                "phone": r["phone"],
                "name": r["name"],
                "role": r["role"] or "user",
                "daily_usage": usage,
                "daily_reset": reset_date
            })
        conn.close()

        # 总用户数
        conn2 = sqlite3.connect(str(USERS_DB))
        cur2 = conn2.execute("SELECT COUNT(*) FROM users")
        total_users = cur2.fetchone()[0]
        conn2.close()

        with STATS_LOCK:
            all_time = USAGE_STATS.get("total_generates", 0)

        return jsonify({
            "date": today,
            "total_users": total_users,
            "active_today": active_today,
            "total_daily_usage": total_daily,
            "all_time_generates": all_time,
            "user_usages": user_usages
        })
