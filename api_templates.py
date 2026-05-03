#!/usr/bin/env python3
"""
模板管理模块 — 模板发现、CRUD、变体、推荐图片
使用 init_routes(app) 模式注册路由
"""
import json, os, hashlib, logging, shutil
from pathlib import Path
from flask import request, jsonify

logger = logging.getLogger(__name__)

# 从主模块引入共享变量
from hyperframes_app import BASE_DIR, JOBS, OUTPUT_DIR, USERS_DB

# ===================== 模板变体系统 =====================

# 每个模板的行业变体配置
TEMPLATE_VARIANTS = {
    "food_promo": {
        "label": "餐饮行业",
        "variants": {
            "火锅": {
                "colors": {"primary": "#d42020", "bg_start": "#3a0a0a", "bg_end": "#1a0505"},
                "keywords": ["麻辣", "毛肚", "锅底", "蘸料", "涮"],
                "voiceover_hint": "鲜香麻辣的锅底，吃一次就忘不了"
            },
            "烧烤": {
                "colors": {"primary": "#e86a20", "bg_start": "#3a1a0a", "bg_end": "#1a0a03"},
                "keywords": ["烤肉", "炭火", "串", "夜宵", "啤酒"],
                "voiceover_hint": "炭火慢烤，每一串都是真功夫"
            },
            "米粉/米线": {
                "colors": {"primary": "#f0a030", "bg_start": "#2a1a0a", "bg_end": "#120a05"},
                "keywords": ["米线", "米粉", "过桥", "汤", "卤"],
                "voiceover_hint": "一碗热汤粉，暖到心里"
            },
            "小吃": {
                "colors": {"primary": "#e8a030", "bg_start": "#2a1a05", "bg_end": "#120a03"},
                "keywords": ["小吃", "路边摊", "特色", "地道"],
                "voiceover_hint": "地道小吃，文山人从小吃到大"
            },
            "奶茶/饮品": {
                "colors": {"primary": "#e87a9a", "bg_start": "#2a0a1a", "bg_end": "#12050a"},
                "keywords": ["奶茶", "果茶", "咖啡", "饮品", "下午茶"],
                "voiceover_hint": "一口好茶，快乐一整天"
            },
        }
    },
    "store_promo": {
        "label": "实体服务行业",
        "variants": {
            "美发": {
                "colors": {"primary": "#8a6ae8", "bg_start": "#1a0a3a", "bg_end": "#0a051a"},
                "keywords": ["剪发", "烫发", "造型", "美发"],
                "voiceover_hint": "做适合你的发型，不只是剪短那么简单"
            },
            "美容/护肤": {
                "colors": {"primary": "#e87a9a", "bg_start": "#2a0a1a", "bg_end": "#12050a"},
                "keywords": ["美容", "护肤", "SPA", "护理"],
                "voiceover_hint": "每一寸肌肤，都值得被温柔对待"
            },
            "健身": {
                "colors": {"primary": "#20c87a", "bg_start": "#0a1a0a", "bg_end": "#030a03"},
                "keywords": ["健身", "减脂", "增肌", "私教"],
                "voiceover_hint": "汗水不会骗你，坚持才能看到改变"
            },
            "家政保洁": {
                "colors": {"primary": "#48b8d0", "bg_start": "#0a1a2a", "bg_end": "#050a12"},
                "keywords": ["家政", "保洁", "打扫", "清洁"],
                "voiceover_hint": "把家交给专业的人，你只管享受生活"
            },
        }
    },
    "product_seed": {
        "label": "产品类型",
        "variants": {
            "服饰": {
                "colors": {"primary": "#d0a0e8", "bg_start": "#1a0a2a", "bg_end": "#0a0515"},
                "keywords": ["衣服", "穿搭", "时尚", "服饰"],
                "voiceover_hint": "穿出你的风格，每一件都是精选"
            },
            "数码": {
                "colors": {"primary": "#40b8f0", "bg_start": "#0a1a3a", "bg_end": "#050a1a"},
                "keywords": ["数码", "科技", "智能", "电子"],
                "voiceover_hint": "科技改变生活，好物值得拥有"
            },
            "家居": {
                "colors": {"primary": "#c8a060", "bg_start": "#1a1208", "bg_end": "#0e0a05"},
                "keywords": ["家居", "家具", "装饰", "收纳"],
                "voiceover_hint": "把家变成你喜欢的样子"
            },
            "食品/零食": {
                "colors": {"primary": "#e8a030", "bg_start": "#2a1a08", "bg_end": "#120a03"},
                "keywords": ["零食", "食品", "好吃", "美味"],
                "voiceover_hint": "好吃不贵，每一口都是满足"
            },
        }
    },
    "farm_promo": {
        "label": "农产品类型",
        "variants": {
            "茶叶": {
                "colors": {"primary": "#5a9a3a", "bg_start": "#0a2a0a", "bg_end": "#030a03"},
                "keywords": ["茶叶", "茶", "绿茶", "红茶", "普洱"],
                "voiceover_hint": "一杯好茶，品味自然"
            },
            "蜂蜜": {
                "colors": {"primary": "#e8b830", "bg_start": "#2a1a05", "bg_end": "#120a02"},
                "keywords": ["蜂蜜", "蜜", "纯天然"],
                "voiceover_hint": "纯粹的甜蜜，来自大自然的馈赠"
            },
            "新鲜水果": {
                "colors": {"primary": "#e87040", "bg_start": "#2a1008", "bg_end": "#120a03"},
                "keywords": ["水果", "鲜果", "当季", "现摘"],
                "voiceover_hint": "自然成熟，现摘现发"
            },
            "山货/特产": {
                "colors": {"primary": "#8a7030", "bg_start": "#1a1005", "bg_end": "#0e0803"},
                "keywords": ["山货", "野生", "土特产", "干货"],
                "voiceover_hint": "山里的好货，城里人吃不到"
            },
        }
    },
    "personal_ip": {
        "label": "个人身份",
        "variants": {
            "创业者": {
                "colors": {"primary": "#d0a030", "bg_start": "#1a1005", "bg_end": "#0e0803"},
                "keywords": ["创业", "创始人", "老板"],
                "voiceover_hint": "在这个领域，我深耕了多年"
            },
            "讲师/教练": {
                "colors": {"primary": "#40a0d0", "bg_start": "#0a1a2a", "bg_end": "#050a15"},
                "keywords": ["教练", "讲师", "老师", "培训"],
                "voiceover_hint": "帮你少走弯路，是我的价值所在"
            },
            "顾问/专家": {
                "colors": {"primary": "#7a60c0", "bg_start": "#0a0520", "bg_end": "#050212"},
                "keywords": ["顾问", "专家", "咨询", "策划"],
                "voiceover_hint": "用专业能力，解决你的核心问题"
            },
        }
    },
    "event_invite": {
        "label": "活动类型",
        "variants": {
            "开业庆典": {
                "colors": {"primary": "#d04020", "bg_start": "#2a0808", "bg_end": "#120305"},
                "keywords": ["开业", "开张", "新店"],
                "voiceover_hint": "新店开张，诚邀您的光临"
            },
            "沙龙/讲座": {
                "colors": {"primary": "#4080d0", "bg_start": "#0a122a", "bg_end": "#050812"},
                "keywords": ["沙龙", "讲座", "分享", "交流会"],
                "voiceover_hint": "一场干货分享，等你来参与"
            },
            "展会/市集": {
                "colors": {"primary": "#e0a030", "bg_start": "#1a1208", "bg_end": "#0e0a05"},
                "keywords": ["展会", "市集", "博览会", "展览"],
                "voiceover_hint": "汇聚好货，只等你来逛"
            },
        }
    },
}

# ===================== 模板推荐图片 =====================

TEMPLATE_IMAGE_KEYWORDS = {
    "food_promo": ["火锅", "科技"],
    "store_promo": ["科技", "个人"],
    "personal_ip": ["个人"],
    "farm_promo": ["农产品"],
    "sanqi_industry": ["农产品"],
    "product_seed": ["科技", "农产品"],
    "event_invite": ["科技"],
    "house_promo": ["科技"],
    "horizontal_promo": ["科技"],
}


# ===================== 辅助函数 =====================

def discover_templates():
    """扫描所有含 template_config.json 的子目录作为模板"""
    templates = []
    for subdir in sorted(BASE_DIR.iterdir()):
        if subdir.is_dir() and (subdir / "template_config.json").exists():
            try:
                with open(subdir / "template_config.json", encoding="utf-8") as f:
                    cfg = json.load(f)
                source = cfg.get("source", "system")
                templates.append({
                    "id": subdir.name,
                    "name": cfg.get("template_name", subdir.name),
                    "description": cfg.get("description", ""),
                    "config": cfg,
                    "path": str(subdir),
                    "source": source
                })
            except Exception as e:
                logger.warning(f"读取模板 {subdir.name} 配置失败: {e}")
    # 自定义模板排在前面
    def sort_key(t):
        return (0 if t["source"] == "custom" else 1, t["id"])
    return sorted(templates, key=sort_key)


def _get_template(template_id):
    for t in discover_templates():
        if t["id"] == template_id:
            return t
    return None


def _get_template_images(template_id: str) -> list:
    """根据模板ID返回对应的免费图库图片列表"""
    from hyperframes_app import PRESET_STOCK_IMAGES
    keywords = TEMPLATE_IMAGE_KEYWORDS.get(template_id, ["科技"])
    seen = set()
    images = []
    for kw in keywords:
        for img in PRESET_STOCK_IMAGES.get(kw, []):
            key = img.get("url", "")
            if key not in seen:
                seen.add(key)
                images.append(img)
    return images


# ===================== 路由注册 =====================

def init_routes(app):
    """注册所有模板管理相关路由"""

    @app.route("/api/templates")
    def api_templates():
        templates = discover_templates()
        return jsonify({"templates": templates})

    @app.route("/api/templates/<template_id>")
    def api_template_detail(template_id):
        for t in discover_templates():
            if t["id"] == template_id:
                return jsonify(t)
        return jsonify({"error": "模板未找到"}), 404

    @app.route("/api/save-template-config", methods=["POST"])
    def api_save_template_config():
        """保存/更新模板配置（template_config.json）"""
        # 认证检查
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
        api_key = auth if auth.startswith("hf_") else request.headers.get("X-API-Key", "")
        if not token and not api_key:
            return jsonify({"error": "未登录或API Key无效"}), 401
        conn = sqlite3.connect(str(USERS_DB))
        row = None
        if api_key:
            cur = conn.execute("SELECT role FROM users WHERE api_key = ?", (api_key,))
            row = cur.fetchone()
        else:
            cur = conn.execute("SELECT role FROM users WHERE token = ?", (token,))
            row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "未登录或API Key无效"}), 401

        data = request.json or {}
        template_id = data.get("template_id", "")
        config = data.get("config", {})

        if not template_id or not config:
            return jsonify({"error": "缺少 template_id 或 config"}), 400

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 404

        config_path = Path(template["path"]) / "template_config.json"
        try:
            # 验证 JSON 可序列化
            json.dumps(config, ensure_ascii=False, indent=2)

            # 备份原配置
            backup_path = config_path.with_suffix(".json.bak")
            if config_path.exists():
                shutil.copy(str(config_path), str(backup_path))

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            logger.info(f"模板配置已保存: {template_id} -> {config_path}")
            return jsonify({"success": True, "message": f"配置已保存到 {template_id}"})
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return jsonify({"error": f"保存失败: {str(e)}"}), 500

    @app.route("/api/template-config/<template_id>", methods=["GET"])
    def api_get_template_config(template_id):
        """获取指定模板的原始 config JSON"""
        template = _get_template(template_id)
        if not template:
            return jsonify({"error": "模板未找到"}), 404
        return jsonify(template["config"])

    @app.route("/api/create-template", methods=["POST"])
    def api_create_template():
        """创建新模板（从已有模板克隆或从零开始）"""
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
        api_key = auth if auth.startswith("hf_") else request.headers.get("X-API-Key", "")
        if not token and not api_key:
            return jsonify({"error": "未登录"}), 401
        conn = sqlite3.connect(str(USERS_DB))
        row = None
        if api_key:
            cur = conn.execute("SELECT role FROM users WHERE api_key = ?", (api_key,))
            row = cur.fetchone()
        else:
            cur = conn.execute("SELECT role FROM users WHERE token = ?", (token,))
            row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "未登录"}), 401

        data = request.json or {}
        action = data.get("action", "clone")  # "clone" or "new"
        source_template_id = data.get("source_template_id", "")
        new_template_id = data.get("new_template_id", "")
        new_template_name = data.get("new_template_name", "我的模板")
        new_description = data.get("new_description", "")

        if not new_template_id:
            # 自动生成ID
            import uuid
            new_template_id = f"custom_{uuid.uuid4().hex[:8]}"

        # 检查ID是否已存在
        existing = _get_template(new_template_id)
        if existing:
            return jsonify({"error": f"模板ID '{new_template_id}' 已存在"}), 400

        new_dir = BASE_DIR / new_template_id
        if new_dir.exists():
            return jsonify({"error": f"目录 '{new_template_id}' 已存在"}), 400

        try:
            new_dir.mkdir(parents=True, exist_ok=False)

            if action == "clone" and source_template_id:
                source_tpl = _get_template(source_template_id)
                if not source_tpl:
                    shutil.rmtree(new_dir, ignore_errors=True)
                    return jsonify({"error": f"源模板 {source_template_id} 不存在"}), 404
                # 复制template_config.json
                src_config = source_tpl["config"]
                new_config = json.loads(json.dumps(src_config))  # deep copy
                new_config["template_id"] = new_template_id
                new_config["template_name"] = new_template_name or (src_config.get("template_name", "") + "（副本）")
                if new_description:
                    new_config["description"] = new_description
                new_config["source"] = "custom"

                # 复制source目录的其他文件
                source_path = Path(source_tpl["path"])
                for f in source_path.iterdir():
                    if f.is_file() and f.name != "template_config.json":
                        try:
                            shutil.copy(str(f), str(new_dir / f.name))
                        except Exception:
                            pass
            else:
                # 从零创建新模板
                new_config = {
                    "template_id": new_template_id,
                    "template_name": new_template_name,
                    "version": "1.0",
                    "description": new_description,
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
                    "background": {
                        "type": "gradient",
                        "options": []
                    },
                    "animation": {
                        "style": "standard",
                        "options": []
                    },
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
                        },
                        {
                            "id": "s2",
                            "name": "内容展示",
                            "duration": 4,
                            "start": 4,
                            "elements": {
                                "line1": {"text": "主要内容", "style": "large_white"},
                                "sub": {"text": "详细说明", "style": "subtitle"}
                            }
                        },
                        {
                            "id": "s3",
                            "name": "结尾",
                            "duration": 4,
                            "start": 8,
                            "elements": {
                                "line1": {"text": "联系我们", "style": "large_gold"},
                                "phone": {"text": "电话：138xxxxxxxx", "style": "phone"}
                            }
                        }
                    ]
                }

            # 写入配置
            config_path = new_dir / "template_config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)

            # 如果目录下没有build_from_config.py，从默认模板复制一个
            build_script = new_dir / "build_from_config.py"
            if not build_script.exists():
                default_build = BASE_DIR / "food_promo" / "build_from_config.py"
                if default_build.exists():
                    shutil.copy(str(default_build), str(build_script))

            logger.info(f"新模板已创建: {new_template_id} (来源: {action}, 源: {source_template_id or '无'})")
            return jsonify({
                "success": True,
                "template_id": new_template_id,
                "template_name": new_config["template_name"],
                "message": f"模板 '{new_config['template_name']}' 创建成功"
            })

        except Exception as e:
            shutil.rmtree(new_dir, ignore_errors=True)
            logger.error(f"创建模板失败: {e}")
            return jsonify({"error": f"创建失败: {str(e)}"}), 500

    @app.route("/api/delete-template", methods=["POST"])
    def api_delete_template():
        """删除模板（仅允许删除自定义模板）"""
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
        if not token:
            return jsonify({"error": "未登录"}), 401
        conn = sqlite3.connect(str(USERS_DB))
        cur = conn.execute("SELECT role FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        conn.close()
        if not row or row[0] != "admin":
            return jsonify({"error": "需要管理员权限"}), 403

        data = request.json or {}
        template_id = data.get("template_id", "")
        if not template_id:
            return jsonify({"error": "缺少 template_id"}), 400

        tpl = _get_template(template_id)
        if not tpl:
            return jsonify({"error": "模板不存在"}), 404

        # 只允许删除自定义模板或管理员强制删除
        config = tpl.get("config", {})
        if config.get("source") != "custom":
            return jsonify({"error": "只能删除自定义模板"}), 400

        try:
            tpl_path = Path(tpl["path"])
            shutil.rmtree(str(tpl_path), ignore_errors=True)
            logger.info(f"模板已删除: {template_id}")
            return jsonify({"success": True, "message": f"模板 '{template_id}' 已删除"})
        except Exception as e:
            return jsonify({"error": f"删除失败: {str(e)}"}), 500

    @app.route("/api/variants")
    def api_variants():
        """返回模板变体列表"""
        result = {}
        for tid, config in TEMPLATE_VARIANTS.items():
            result[tid] = {
                "label": config["label"],
                "variants": list(config["variants"].keys())
            }
        return jsonify(result)

    @app.route("/api/variant-config", methods=["POST"])
    def api_variant_config():
        """返回某个变体的配色配置"""
        data = request.json or {}
        tid = data.get("template_id", "")
        variant = data.get("variant", "")

        tpl_var = TEMPLATE_VARIANTS.get(tid)
        if not tpl_var:
            return jsonify({"error": "模板无变体配置"}), 404

        var_data = tpl_var["variants"].get(variant)
        if not var_data:
            return jsonify({"error": "变体未找到"}), 404

        return jsonify({
            "template_id": tid,
            "variant": variant,
            "colors": var_data["colors"],
            "keywords": var_data["keywords"],
            "voiceover_hint": var_data["voiceover_hint"]
        })

    @app.route("/api/template-images", methods=["POST"])
    def api_template_images():
        """返回模板对应的免费图库图片列表"""
        data = request.json or {}
        template_id = data.get("template_id", "")
        if not template_id:
            return jsonify({"error": "缺少template_id"}), 400
        images = _get_template_images(template_id)
        return jsonify({"images": images})
