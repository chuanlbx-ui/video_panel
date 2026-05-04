#!/usr/bin/env python3
"""
api_video.py — 视频渲染/生成/下载模块
从 hyperframes_app.py 拆分而来
"""

import json, os, sys, uuid, subprocess, threading, smtplib, shutil, hashlib, time, logging, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify, send_file

from hyperframes_app import BASE_DIR, OUTPUT_DIR, JOBS, JOBS_LOCK, ASSETS_DIR, BG_LOOPS_DIR, USERS_DB, STATS_LOCK, BATCH_QUEUE, USAGE_STATS, logger

# 定义持久化文件路径
JOBS_FILE = BASE_DIR / "jobs.json"
from api_templates import discover_templates, _get_template, TEMPLATE_VARIANTS
from build_engine import generate_tts, merge_audio, get_color_scheme, download_bgm, check_cache

try:
    from llm_client import llm_match_template, llm_optimize_copy
    _LLM_AVAILABLE = True
    logger.info("[V5.0] LLM客户端就绪 — 智能匹配 + 文案优化")
except ImportError:
    _LLM_AVAILABLE = False
    logger.warning("[V5.0] llm_client.py 未找到，使用关键词匹配回退")
except Exception as e:
    _LLM_AVAILABLE = False
    logger.warning(f"[V5.0] llm_client 加载异常: {e}，使用关键词匹配回退")

# ===================== 免费图库预设 =====================
# 预设高质量免费图片库，按关键词分类，无需API Key即可使用
PRESET_STOCK_IMAGES = {
    "火锅": [
        {"url": "https://images.pexels.com/photos/699953/pexels-photo-699953.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/699953/pexels-photo-699953.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "热气腾腾的火锅", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/941861/pexels-photo-941861.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/941861/pexels-photo-941861.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "火锅食材摆盘", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/16513704/pexels-photo-16513704.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/16513704/pexels-photo-16513704.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "鸳鸯火锅", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/11341782/pexels-photo-11341782.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/11341782/pexels-photo-11341782.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "火锅聚餐", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/963015/pexels-photo-963015.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/963015/pexels-photo-963015.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "美食火锅", "source": "pexels"},
    ],
    "科技": [
        {"url": "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "科技未来感", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "数码科技", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/2582937/pexels-photo-2582937.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2582937/pexels-photo-2582937.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "人工智能", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/577585/pexels-photo-577585.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/577585/pexels-photo-577585.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "电路板细节", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/355948/pexels-photo-355948.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/355948/pexels-photo-355948.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "编程代码", "source": "pexels"},
    ],
    "农产品": [
        {"url": "https://images.pexels.com/photos/2255792/pexels-photo-2255792.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2255792/pexels-photo-2255792.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "新鲜蔬菜", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/4114219/pexels-photo-4114219.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/4114219/pexels-photo-4114219.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "水果种植", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/2886937/pexels-photo-2886937.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2886937/pexels-photo-2886937.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "稻田", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/1278133/pexels-photo-1278133.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1278133/pexels-photo-1278133.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "农场风光", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/2403392/pexels-photo-2403392.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2403392/pexels-photo-2403392.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "茶山", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/1071882/pexels-photo-1071882.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1071882/pexels-photo-1071882.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "三七药材", "source": "pexels"},
    ],
    "个人": [
        {"url": "https://images.pexels.com/photos/2379004/pexels-photo-2379004.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2379004/pexels-photo-2379004.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "自信的人像", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/3763188/pexels-photo-3763188.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/3763188/pexels-photo-3763188.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "职场人士", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/5212361/pexels-photo-5212361.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/5212361/pexels-photo-5212361.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "讲师授课", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/4065184/pexels-photo-4065184.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/4065184/pexels-photo-4065184.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "创业故事", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/3194518/pexels-photo-3194518.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/3194518/pexels-photo-3194518.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "团队合照", "source": "pexels"},
    ],
    "教育": [
        {"url": "https://images.pexels.com/photos/301926/pexels-photo-301926.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/301926/pexels-photo-301926.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "课堂学习", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/159844/cellular-education-classroom-159844.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/159844/cellular-education-classroom-159844.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "实验室", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/4145153/pexels-photo-4145153.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/4145153/pexels-photo-4145153.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "学生编程", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/256455/pexels-photo-256455.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/256455/pexels-photo-256455.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "书籍学习", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/5905493/pexels-photo-5905493.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/5905493/pexels-photo-5905493.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "在线教育", "source": "pexels"},
    ],
    "咖啡": [
        {"url": "https://images.pexels.com/photos/374757/pexels-photo-374757.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/374757/pexels-photo-374757.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "咖啡拉花", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/302899/pexels-photo-302899.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/302899/pexels-photo-302899.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "咖啡豆", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/169793/pexels-photo-169793.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/169793/pexels-photo-169793.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "咖啡店", "source": "pexels"},
    ],
    "健身": [
        {"url": "https://images.pexels.com/photos/1552242/pexels-photo-1552242.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1552242/pexels-photo-1552242.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "健身房", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/2294361/pexels-photo-2294361.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2294361/pexels-photo-2294361.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "跑步运动", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/841130/pexels-photo-841130.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/841130/pexels-photo-841130.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "瑜伽", "source": "pexels"},
    ],
    "旅游": [
        {"url": "https://images.pexels.com/photos/417074/pexels-photo-417074.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/417074/pexels-photo-417074.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "山水风景", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/1190297/pexels-photo-1190297.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1190297/pexels-photo-1190297.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "古镇", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/206660/pexels-photo-206660.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/206660/pexels-photo-206660.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "海滩", "source": "pexels"},
    ],
    "美食": [
        {"url": "https://images.pexels.com/photos/958545/pexels-photo-958545.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/958545/pexels-photo-958545.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "精致美食", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/704569/pexels-photo-704569.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/704569/pexels-photo-704569.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "甜品", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/262959/pexels-photo-262959.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/262959/pexels-photo-262959.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "烧烤", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/1640770/pexels-photo-1640770.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1640770/pexels-photo-1640770.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "中式糕点", "source": "pexels"},
    ],
    "自然": [
        {"url": "https://images.pexels.com/photos/1001682/pexels-photo-1001682.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1001682/pexels-photo-1001682.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "森林", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/417344/pexels-photo-417344.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/417344/pexels-photo-417344.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "日落", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/2387873/pexels-photo-2387873.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/2387873/pexels-photo-2387873.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "花朵", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/531880/pexels-photo-531880.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/531880/pexels-photo-531880.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "星空", "source": "pexels"},
    ],
    "建筑": [
        {"url": "https://images.pexels.com/photos/323780/pexels-photo-323780.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/323780/pexels-photo-323780.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "现代建筑", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/290595/pexels-photo-290595.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/290595/pexels-photo-290595.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "城市天际线", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/460672/pexels-photo-460672.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/460672/pexels-photo-460672.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "古建筑", "source": "pexels"},
    ],
    "茶饮": [
        {"url": "https://images.pexels.com/photos/1417942/pexels-photo-1417942.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/1417942/pexels-photo-1417942.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "茶艺", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/302680/pexels-photo-302680.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/302680/pexels-photo-302680.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "奶茶", "source": "pexels"},
        {"url": "https://images.pexels.com/photos/129207/pexels-photo-129207.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=1", "thumb_url": "https://images.pexels.com/photos/129207/pexels-photo-129207.jpeg?auto=compress&cs=tinysrgb&w=400&h=300&dpr=1", "description": "中式茶馆", "source": "pexels"},
    ],
}

STOCK_KEYWORDS = list(PRESET_STOCK_IMAGES.keys())

def search_stock_images(keyword: str, count: int = 5) -> list:
    """搜索免费图库图片，模糊匹配预设关键词"""
    keyword_lower = keyword.lower().strip()
    results = []

    # 精确匹配 + 模糊匹配
    matched_key = None
    for key in STOCK_KEYWORDS:
        if key.lower() == keyword_lower:
            matched_key = key
            break

    if not matched_key:
        # 模糊匹配：关键词包含或被包含
        for key in STOCK_KEYWORDS:
            if keyword_lower in key.lower() or key.lower() in keyword_lower:
                matched_key = key
                break

    if not matched_key:
        # 按行业词根匹配
        industry_map = {
            "餐饮": "美食", "饭店": "美食", "餐厅": "美食", "小吃": "美食",
            "推广": "科技", "广告": "科技", "营销": "科技",
            "农业": "农产品", "养殖": "农产品", "种植": "农产品",
            "医生": "个人", "教师": "教育", "老师": "教育", "培训": "教育",
            "水果": "农产品", "蔬菜": "农产品", "奶茶": "茶饮", "茶": "茶饮",
            "酒": "美食", "装修": "建筑", "房产": "建筑", "设计": "建筑",
            "编程": "科技", "互联网": "科技", "手机": "科技",
            "旅游": "旅游", "酒店": "旅游", "民宿": "旅游",
            "美容": "个人", "美发": "个人", "养生": "个人",
            "瑜伽": "健身", "运动": "健身", "体育": "健身",
        }
        for k, v in industry_map.items():
            if k in keyword_lower:
                matched_key = v
                break

    if matched_key and matched_key in PRESET_STOCK_IMAGES:
        images = PRESET_STOCK_IMAGES[matched_key]
        results = images[:count]

    # 如果没匹配到，返回所有图片的前几张作为通用推荐
    if not results:
        fallback = []
        for key in STOCK_KEYWORDS:
            fallback.extend(PRESET_STOCK_IMAGES[key])
            if len(fallback) >= count:
                break
        results = fallback[:count]

    return results

def merge_config_with_user(template_config: dict, user_params: dict, is_preview: bool = False) -> dict:
    """V3: 合并模板默认配置+用户参数（含背景/字幕/新参数）"""
    merged = json.loads(json.dumps(template_config))  # 深拷贝

    # 确保 effects 键存在
    if "effects" not in merged:
        merged["effects"] = {
            "transition_style": "fade",
            "particle_density": "medium",
            "glow_enabled": False
        }

    # 1) 文案替换
    text_config = user_params.get("text", {})
    for scene in merged.get("scenes", []):
        s_id = scene["id"]
        if s_id in text_config:
            for key, val in text_config[s_id].items():
                if key in scene.get("elements", {}):
                    scene["elements"][key]["text"] = val

    # 1.5) 场景时长覆盖（用户可自定义每个场景时长）
    durations = user_params.get("durations", {})
    for scene in merged.get("scenes", []):
        s_id = scene["id"]
        if s_id in durations:
            scene["duration"] = durations[s_id]

    # 2) 配色方案
    scheme = user_params.get("colors", "")
    if scheme:
        merged["colors"]["scheme"] = scheme

    # 3) 动画风格
    anim = user_params.get("animation", "")
    if anim:
        merged["animation"]["style"] = anim

    # 4) 背景类型
    bg_type = user_params.get("bg_type", "")
    if bg_type:
        merged["background"]["type"] = bg_type
        merged["settings"]["bg_type"] = bg_type

    # 5) 配音
    vo = user_params.get("voiceover", {})
    if "enabled" in vo:
        merged["audio"]["voiceover"]["enabled"] = vo["enabled"]
    if "text" in vo:
        merged["audio"]["voiceover"]["text"] = vo["text"]
    if "voice" in vo:
        merged["audio"]["voiceover"]["voice"] = vo["voice"]

    # 6) BGM
    bgm = user_params.get("bgm", {})
    if "enabled" in bgm:
        merged["audio"]["bgm"]["enabled"] = bgm["enabled"]
    if "file" in bgm and bgm["file"]:
        merged["audio"]["bgm"]["file"] = bgm["file"]

    # 7) 字幕
    subs = user_params.get("subtitles", {})
    if "enabled" in subs:
        if "subtitles" not in merged:
            merged["subtitles"] = {}
        merged["subtitles"]["enabled"] = subs["enabled"]

    # 7.5) 个性化设置：自定义背景、配色偏好、品牌水印
    user_bg = user_params.get("user_bg", "")
    user_bg_duration = user_params.get("user_bg_duration", 4.0)
    if user_bg:
        merged["custom_bg"] = user_bg
        # 将单张背景图转换为 background 配置，供渲染引擎使用
        merged["background"] = {
            "type": "image",
            "url": user_bg,
            "duration": user_bg_duration
        }
        logger.info(f"[背景] 已应用单张背景图: {user_bg[:60]}...")
    user_color_scheme = user_params.get("user_color_scheme", "")
    if user_color_scheme:
        merged["user_color_scheme"] = user_color_scheme
    user_brand_watermark = user_params.get("user_brand_watermark", "")
    if user_brand_watermark:
        merged["user_brand_watermark"] = user_brand_watermark

    # 8) 质量设置 — 新增 pro 档位（20M码率 + 10bit）
    quality = user_params.get("quality", "standard")
    merged["settings"]["quality"] = quality
    if quality == "pro":
        merged["settings"]["video_bitrate"] = "20M"
        merged["settings"]["pixel_format"] = "yuv420p10le"
    elif quality == "high":
        merged["settings"]["video_bitrate"] = "15M"
        merged["settings"]["pixel_format"] = "yuv420p"
    elif quality == "draft":
        merged["settings"]["video_bitrate"] = "5M"
        merged["settings"]["pixel_format"] = "yuv420p"
        merged["settings"]["fps"] = 10
    else:
        merged["settings"]["video_bitrate"] = "10M"
        merged["settings"]["pixel_format"] = "yuv420p"

    # 9) 特效参数 — 转场/粒子密度/辉光
    effects = user_params.get("effects", {})
    if effects.get("transition_style"):
        merged["effects"]["transition_style"] = effects["transition_style"]
    if effects.get("particle_density"):
        merged["effects"]["particle_density"] = effects["particle_density"]
    if "glow_enabled" in effects:
        merged["effects"]["glow_enabled"] = effects["glow_enabled"]

    # 10) 预览模式
    if is_preview:
        w, h = merged["settings"].get("output_width", 1080), merged["settings"].get("output_height", 1920)
        ratio = min(540/w, 960/h)
        merged["settings"]["output_width"] = int(w * ratio)
        merged["settings"]["output_height"] = int(h * ratio)
        merged["settings"]["quality"] = "draft"
        merged["settings"]["video_bitrate"] = "3M"
        merged["settings"]["fps"] = 24
        merged["audio"]["bgm"]["enabled"] = False
        merged["audio"]["voiceover"]["enabled"] = False
        if "subtitles" in merged:
            merged["subtitles"]["enabled"] = False

    # 11) 素材混剪
    mix_media = user_params.get("mix_media", [])
    if mix_media:
        merged["mix_media"] = mix_media
        merged["mix_mode"] = user_params.get("mix_mode", "bg_only")

    # 11.5) 多背景场景组合（user_bg_scenes）
    user_bg_scenes = user_params.get("user_bg_scenes", [])
    if user_bg_scenes:
        merged["user_bg_scenes"] = user_bg_scenes
        merged["settings"]["bg_scenes"] = user_bg_scenes
        # 转换为 background 配置（image_sequence类型），供渲染引擎使用
        bg_list = []
        for i, s in enumerate(user_bg_scenes):
            bg_list.append({
                "id": s.get("id", f"bg_{i}"),
                "url": s.get("url", ""),
                "duration": s.get("duration", 4.0),
                "sort_order": s.get("sort_order", i)
            })
        merged["background"] = {
            "type": "image_sequence",
            "images": bg_list,
            "total_duration": sum(img.get("duration", 4.0) for img in bg_list)
        }
        logger.info(f"[背景组合] 已应用 {len(bg_list)} 张背景图, 总时长 {merged['background']['total_duration']}s")

    # 12) 动态排版随机感 — 注入抖动种子
    # 从用户参数或 job_id 派生确定性种子，保证同一 job 多次运行结果一致
    raw_seed = user_params.get("_jitter_seed", None)
    if raw_seed is None:
        # 用当前时间戳的确定性部分作为回退
        import time
        raw_seed = int(time.time() * 1000) & 0x7FFFFFFF
    merged["_jitter"] = {
        "enabled": True,
        "job_seed": raw_seed,
        "font_size_range": 2,       # ±2px
        "margin_top_range_pct": 5.0, # ±5%
        "particle_mult_min": 0.7,
        "particle_mult_max": 1.3,
    }

    return merged


def _update_progress(job_id: str, progress: int):
    """线程安全更新进度并持久化"""
    try:
        if job_id in JOBS:
            JOBS[job_id]["progress"] = progress
            jobs_save(job_id)
    except Exception:
        pass

def _run_with_progress(cmd: list, job_id: str, cwd: str = None,
                       timeout: int = 600, start_pct: int = 5, end_pct: int = 80):
    """以异步Popen运行子进程，同时每3秒递增进度"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=cwd)
    import threading as _th
    step = (end_pct - start_pct) // 8  # 分8步递增
    current = start_pct
    stop_flag = [False]

    def _monitor():
        nonlocal current
        while not stop_flag[0] and current < end_pct:
            current = min(current + step, end_pct)
            _update_progress(job_id, current)
            time.sleep(3)

    t = _th.Thread(target=_monitor, daemon=True)
    t.start()

    stdout, stderr = proc.communicate(timeout=timeout)
    stop_flag[0] = True
    t.join(timeout=2)

    return stdout, stderr, proc.returncode

def render_video(template_dir: Path, config: dict, job_id: str):
    """V3: 调用build_from_config.py渲染+音频合成+字幕 (优化版: 缓存+多核) 带实时进度"""
    try:
        # ===== 缓存检查 =====
        cache_key = hashlib.md5(json.dumps(config, sort_keys=True).encode()).hexdigest()
        cache_path = OUTPUT_DIR / f"cache_{cache_key}.mp4"
        if cache_path.exists():
            # 检查缓存文件是否在7天内
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age < 7 * 86400:
                logger.info(f"作业 {job_id}: 命中缓存 cache_{cache_key}.mp4，跳过渲染")
                output_path = OUTPUT_DIR / f"{job_id}.mp4"
                shutil.copy(str(cache_path), str(output_path))
                JOBS[job_id]["status"] = "completed"
                JOBS[job_id]["output"] = str(output_path)
                JOBS[job_id]["progress"] = 100
                jobs_save(job_id)
                logger.info(f"作业 {job_id} 完成(缓存): {output_path} ({output_path.stat().st_size} bytes)")
                record_usage(job_id, "completed")
                record_user_video(job_id)
                return
            else:
                # 过期缓存删除
                cache_path.unlink(missing_ok=True)
                logger.info(f"作业 {job_id}: 缓存已过期，重新渲染")

        temp_config = template_dir / f"config_{job_id}.json"
        with open(temp_config, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        build_script = template_dir / "build_from_config.py"
        if not build_script.exists():
            raise FileNotFoundError(f"未找到构建脚本: {build_script}")

        quality = config.get('settings', {}).get('quality', 'standard')
        logger.info(f"作业 {job_id}: 构建脚本={build_script.name}, "
                     f"quality={quality}, "
                     f"bg_type={config.get('background',{}).get('type','gradient')}, "
                     f"subtitles={config.get('subtitles',{}).get('enabled',False)}")

        cmd = [sys.executable, str(build_script),
               "--config", str(temp_config),
               "--render"]
        # 带实时进度：5% → 80%
        _update_progress(job_id, 5)
        stdout, stderr, rc = _run_with_progress(cmd, job_id, cwd=str(template_dir),
                                                  timeout=600, start_pct=5, end_pct=80)
        if rc != 0:
            err = stderr[:500] if stderr else stdout[:500]
            raise RuntimeError(f"渲染失败: {err}")

        # 找输出文件
        final_candidates = [
            template_dir / "output_final.mp4",
            template_dir / "output.mp4",
            template_dir / "raw_output.mp4"
        ]
        final_video = None
        for f in final_candidates:
            if f.exists():
                final_video = f
                break

        if not final_video:
            for f in OUTPUT_DIR.glob("*.mp4"):
                final_video = f
                break

        if not final_video:
            raise RuntimeError("未找到输出文件")

        output_path = OUTPUT_DIR / f"{job_id}.mp4"
        shutil.copy(str(final_video), str(output_path))

        # ===== 叠加心学金句水印（V4.8） =====
        _update_progress(job_id, 80)
        _watermark_applied = False
        try:
            # 先检查PIL是否可用
            import importlib
            try:
                importlib.import_module('PIL')
            except ImportError:
                raise ImportError("PIL未安装")

            from PIL import Image, ImageDraw, ImageFont
            wm_png = OUTPUT_DIR / f"wm_{job_id}.png"

            QUOTES = [
                ("心即理", "心外无物，心外无理"),
                ("致良知", "知善知恶是良知"),
                ("知行合一", "知而不行，只是未知"),
                ("心即理", "此心光明，亦复何言"),
                ("致良知", "人人自有定盘针"),
                ("知行合一", "事上磨练，方立得住"),
                ("心即理", "破山中贼易，破心中贼难"),
                ("致良知", "减得一分人欲，便复得一分天理"),
                ("知行合一", "未有知而不行者，知而不行只是未知"),
                ("滇边AI", "心学智造 · 知行合一"),
                ("文山州互联网协会", "从投资物到投资人"),
                ("滇边AI", "AI数字工匠 · 致良知"),
            ]
            idx = abs(hash(job_id)) % len(QUOTES)
            title, body = QUOTES[idx]

            w = config.get("settings", {}).get("output_width", 1080)
            h = config.get("settings", {}).get("output_height", 1920)
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            fp = None
            for f in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                       "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
                       "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
                       "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]:
                if os.path.exists(f): fp = f; break
            try:
                ft = ImageFont.truetype(fp or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
                fb = ImageFont.truetype(fp or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            except:
                ft = fb = ImageFont.load_default()

            bar_h = 110
            bar_y = h - bar_h - 30
            # 检查是否有用户自定义品牌水印
            user_brand_wm = config.get("user_brand_watermark", "")
            if user_brand_wm:
                # 使用用户品牌水印替代默认的心学金句
                bar_h = 90
                bar_y = h - bar_h - 30
                for y in range(bar_y, h):
                    a = int(160 * (1 - (y - bar_y) / bar_h))
                    if a > 0:
                        draw.rectangle([0, y, w, y+1], fill=(6, 14, 30, min(a, 180)))
                draw.rectangle([w - 420, bar_y + 18, w - 30, bar_y + 22], fill=(255, 213, 79, 220))
                ft_brand = ImageFont.truetype(fp or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
                tb = draw.textbbox((0, 0), user_brand_wm, font=ft_brand)
                mw = tb[2] - tb[0]
                draw.text((w - 30 - mw, bar_y + 32), user_brand_wm, fill=(255, 213, 79, 230), font=ft_brand)
                draw.text((w - 30 - mw, bar_y + 65), "AI数字工匠 · 致良知", fill=(255, 255, 255, 150), font=fb)
            else:
                for y in range(bar_y, h):
                    a = int(160 * (1 - (y - bar_y) / bar_h))
                    if a > 0:
                        draw.rectangle([0, y, w, y+1], fill=(6, 14, 30, min(a, 180)))

                draw.rectangle([w - 420, bar_y + 18, w - 30, bar_y + 22], fill=(255, 213, 79, 220))

                t_text = f"✦ {title}"
                b_text = f"「{body}」"
                tb = draw.textbbox((0, 0), t_text, font=ft)
                bb = draw.textbbox((0, 0), b_text, font=fb)
                mw = max(tb[2]-tb[0], bb[2]-bb[0])
                draw.text((w - 30 - mw, bar_y + 32), t_text, fill=(255, 213, 79, 230), font=ft)
                draw.text((w - 30 - mw, bar_y + 80), b_text, fill=(255, 255, 255, 180), font=fb)

            img.save(str(wm_png), "PNG")

            if wm_png.exists() and wm_png.stat().st_size > 100:
                temp_wm = OUTPUT_DIR / f"{job_id}_wm_temp.mp4"
                r = subprocess.run([
                    "ffmpeg", "-y",
                    "-i", str(output_path),
                    "-i", str(wm_png),
                    "-filter_complex", "[0:v][1:v]overlay=W-w-40:H-h-40",
                    "-c:a", "copy",
                    str(temp_wm)
                ], capture_output=True, text=True, timeout=120)
                if temp_wm.exists():
                    temp_wm.replace(output_path)
                    _watermark_applied = True
                wm_png.unlink(missing_ok=True)
        except Exception as wm_err:
            pass  # 静默失败，不影响视频
        if _watermark_applied:
            logger.info(f"作业 {job_id}: 心学金句水印叠加完成")

        _update_progress(job_id, 95)

        # ===== 写入缓存 =====
        try:
            shutil.copy(str(output_path), str(cache_path))
            logger.info(f"作业 {job_id}: 已写入缓存 cache_{cache_key}.mp4")
        except Exception as cache_err:
            logger.warning(f"作业 {job_id}: 缓存写入失败: {cache_err}")

        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["output"] = str(output_path)
        JOBS[job_id]["progress"] = 100
        jobs_save(job_id)
        logger.info(f"作业 {job_id} 完成: {output_path} ({output_path.stat().st_size} bytes)")
        record_usage(job_id, "completed")
        record_user_video(job_id)

        if temp_config.exists():
            temp_config.unlink()

    except subprocess.TimeoutExpired:
        jobs_update_status(job_id, "failed", error="渲染超时")
        logger.error(f"作业 {job_id} 超时")
        record_usage(job_id, "failed")
    except Exception as e:
        jobs_update_status(job_id, "failed", error=str(e))
        logger.error(f"作业 {job_id} 失败: {e}")
        record_usage(job_id, "failed")

def _get_template(template_id):
    for t in discover_templates():
        if t["id"] == template_id:
            return t
    return None

def _generate_copy(brand, desc, phone, address, template_id="food_promo", value="", price=""):
    """根据用户输入生成走心视频文案（升级版：句式多样、情感丰富）"""
    desc = desc or ""
    desc_lower = desc.lower()

    # 传入语气参数（根据模板类型自动选择）
    if template_id == "food_promo":
        return _gen_copy_food(brand, desc, phone, address)
    elif template_id == "event_invite":
        return _gen_copy_event(brand, desc, phone, address)
    elif template_id in ("personal_ip", "personal_ip_v1"):
        return _gen_copy_ip(brand, desc, phone, value)
    elif template_id in ("product_seed", "product_seed_v1"):
        return _gen_copy_product(brand, desc, value, price, phone)
    elif template_id == "sanqi_industry":
        return _gen_copy_sanqi(brand, desc, phone, address)
    elif template_id == "association_invite":
        return _gen_copy_association(brand, desc, phone, address)
    elif template_id in ("store_promo", "store_promo_v1"):
        return _gen_copy_store(brand, desc, phone, address)
    elif template_id in ("farm_promo", "farm_promo_v1"):
        return _gen_copy_farm(brand, desc, price, phone)
    else:
        return _gen_copy_general(brand, desc, phone)


def _generate_copy_v2(brand, desc, phone, address, template_id="food_promo",
                      value="", price="", tone="auto"):
    """
    升级版文案生成引擎。

    参数:
        tone: 语气风格 - "auto" / "warm" / "professional" / "hip" / "emotional" / "minimalist"

    比 _generate_copy 多出:
    - 5种以上文案结构（设问式、对比式、故事式、金句式、场景式）
    - 语气风格控制
    - 金句库随机插入
    - 更丰富的场景描述
    """
    # 选择基础生成函数
    result = _generate_copy(brand, desc, phone, address, template_id, value, price)

    # 用金句库提升文案质感
    result = _apply_golden_phrases(result, template_id, tone)

    return result


def _llm_copy_with_fallback(template_id, brand, desc, address, phone, value="", price=""):
    """
    统一文案生成入口：优先 LLM，失败回退规则引擎。

    在 _generate_copy 的上下文（brand, desc, phone, address, template_id, value, price）
    和 llm_optimize_copy 的上下文（template_id, brand, desc, address, phone, value, price）
    之间做适配。
    """
    if _LLM_AVAILABLE:
        opt_result = llm_optimize_copy(template_id, brand, desc, address, phone, value=value, price=price)
        if isinstance(opt_result, dict) and opt_result.get("scene_texts"):
            return {
                "scene_texts": opt_result["scene_texts"],
                "voiceover_text": opt_result.get("voiceover_text", "")
            }
        # LLM 返回无效结果，回退到规则引擎
    # LLM 不可用或返回无效结果
    return _generate_copy(brand, desc, phone, address, template_id=template_id, value=value, price=price)


# ═══════════════════ 金句库 ═══════════════════

_GOLDEN_PHRASES = {
    "food_promo": [
        "人间烟火气，最抚凡人心。",
        "好的味道，不需要故事，一口就知道。",
        "把时间花在美食上，就不算虚度。",
        "没有什么是一顿饭解决不了的，如果有，就两顿。",
        "吃是一种幸福，品是一种享受。",
        "世界再大，不过一碗人间烟火。",
        "味道是有记忆的，一口回到小时候。",
        "生活的滋味，酸甜苦辣，都在这一碗里。",
    ],
    "store_promo": [
        "用心的人，值得被用心对待。",
        "把平凡的事做好，就是不平凡。",
        "专业，就是把细节做到极致。",
        "你的每一分钱，都花在看得见的地方。",
        "服务没有最好，只有更好。",
        "用匠心，换你一个放心。",
    ],
    "personal_ip": [
        "做自己，是最好的个人品牌。",
        "与其更好，不如不同。",
        "专业不是标签，是日复一日的坚持。",
        "你的经验，就是别人最好的避坑指南。",
        "帮别人解决问题，就是最大的价值。",
    ],
    "product_seed": [
        "好的产品，自己会说话。",
        "种草容易，拔草难。但好东西，值得拥有。",
        "买对不买贵，选对才省心。",
        "用过之后，你就回不去了。",
        "你的生活品质，从选对一件好物开始。",
    ],
    "event_invite": [
        "与其在别处仰望，不如在这里并肩。",
        "有些机会，错过了就不会再来。",
        "见一面，胜过千言万语。",
        "来都来了，总得带走点什么。",
        "一群人，一件事，一起做。",
    ],
    "farm_promo": [
        "好山好水出好物，大自然的馈赠。",
        "从田间到舌尖，品质看得见。",
        "慢生长，才够味。",
        "不打农药不催熟，时间酿出的甜。",
    ],
    "education": [
        "最好的投资，是投资自己。",
        "学习，是唯一稳赚不赔的买卖。",
        "种一棵树最好的时间是十年前，其次是现在。",
        "你的认知边界，决定你的世界大小。",
    ],
    "general": [
        "用心，一切皆有可能。",
        "最好的关系，是彼此成就。",
        "机会留给有准备的人，也留给有行动的人。",
        "你想要的，时间都会给你。",
    ],
}

_GOLDEN_OPENERS = [
    "你有没有想过——",
    "你知道吗？",
    "说实话，",
    "我敢说，",
    "说真的，",
    "悄悄告诉你，",
    "你相信吗？",
    "就这么简单——",
    "不卖关子了，",
    "你可能不知道，",
]


def _apply_golden_phrases(result, template_id, tone="auto"):
    """对生成的文案应用金句库，提升文案质感"""
    voiceover = result.get("voiceover_text", "")
    if not voiceover:
        return result

    # 选择对应模板的金句库
    if template_id in ("food_promo", "restaurant_promo_v1"):
        pool = _GOLDEN_PHRASES["food_promo"]
    elif template_id in ("store_promo", "store_promo_v1"):
        pool = _GOLDEN_PHRASES["store_promo"]
    elif template_id in ("personal_ip", "personal_ip_v1"):
        pool = _GOLDEN_PHRASES["personal_ip"]
    elif template_id in ("product_seed", "product_seed_v1"):
        pool = _GOLDEN_PHRASES["product_seed"]
    elif template_id == "event_invite":
        pool = _GOLDEN_PHRASES["event_invite"]
    elif template_id in ("farm_promo", "farm_promo_v1", "sanqi_industry"):
        pool = _GOLDEN_PHRASES["farm_promo"]
    elif template_id in ("edu_recruit", "course_promo", "xinxue_course"):
        pool = _GOLDEN_PHRASES["education"]
    else:
        pool = _GOLDEN_PHRASES["general"]

    import random
    golden = random.choice(pool) if pool else ""
    opener = random.choice(_GOLDEN_OPENERS)

    # 根据语气风格插入金句
    if tone == "minimalist":
        # 极简风不加金句
        pass
    elif tone == "emotional":
        # 情感风插入在金句后
        voiceover = golden + " " + voiceover
    elif tone == "hip":
        # 潮酷风用开场
        voiceover = opener + " " + voiceover
    else:
        # 默认：随机决定是否插入
        if random.random() < 0.5 and golden:
            voiceover = golden + " " + voiceover

    result["voiceover_text"] = voiceover
    return result


def _gen_copy_general(title, desc, phone):
    """通用模板文案生成（升级版：横版宣传、小红书、AI日报等）"""
    desc = desc or ""
    import random

    phone_str = f"📞 {phone}" if phone else ""

    # ── 多样化的开场 ──
    openers = [
        f"你好，{title}。{desc}",
        f"今天要给你介绍的是——{title}。",
        f"说真的，{title}值得你花两分钟了解一下。",
        f"你听说过{title}吗？今天来好好聊聊。",
        f"如果你对{desc or '这个话题'}感兴趣，那你一定要认识{title}。",
    ]
    opener = random.choice(openers)

    closers = [
        f"如果你感兴趣，欢迎联系我们。{phone_str}期待与你相遇。",
        f"机会难得，别错过了。{phone_str}",
        f"更多精彩，等你来发现。{phone_str}",
        f"期待和你有更多的交流。{phone_str}",
    ]
    closer = random.choice(closers)

    voiceover = f"{opener}。{closer}"

    scene_texts = {
        "s1": {"line1": title, "line2": desc or "精彩内容", "sub": phone_str}
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_sanqi(brand, desc, phone, address):
    """三七产业模板文案生成（升级版）"""
    desc = desc or ""
    import random

    address_str = f"📍 {address}" if address else ""
    phone_str = f"📞 {phone}" if phone else ""

    openers = [
        f"文山三七，天下闻名。{brand}{': ' + desc if desc else ''}",
        f"你知道三七为什么叫\"金不换\"吗？{brand}告诉你答案。",
        f"说到养生，就不能不提三七。{brand}，道地文山三七。",
        f"如果你也在关注养生，那你一定听说过{brand}的三七。",
    ]
    opener = random.choice(openers)

    middles = [
        "道地药材，药食同源。三七总皂苷含量丰富，活血化瘀、消肿定痛。",
        "从种植到加工，每一个环节都严格把关。品质，是立身之本。",
        "好三七，看产地、看含量、看成色。文山三七，每一颗都是精华。",
    ]
    middle = random.choice(middles)

    closers = [
        f"想了解三七的养生之道？欢迎联系我。{phone_str}",
        f"养生这件事，从选对一味好三七开始。{phone_str}",
        f"每天3-9克，养生从今天开始。{phone_str}",
    ]
    closer = random.choice(closers)

    voiceover = f"{opener} {middle} {closer}"

    scene_texts = {
        "s1": {"line1": "南国神草", "line2": "文山三七", "sub": f"{brand} · 道地药材"},
        "s2": {"line1": brand, "line2": desc or "品质之选", "line3": "药食同源 · 养生佳品", "sub": address_str or "源自三七之乡"},
        "s3": {"line1": "选三七", "line2": "看产地 · 看含量 · 看成色", "sub": "道地药材，精华所在"},
        "s4": {"line1": "怎么吃三七", "line2": "打粉冲服 · 炖汤煲粥", "sub": "每日3-9克，养生从今天开始"},
        "s5": {"price": "限时优惠", "info": f"{phone_str}", "limit": "咨询购买"},
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_association(brand, desc, phone, address):
    """协会邀请函模板文案生成（升级版）"""
    desc = desc or ""
    import random

    address_str = f"📍 {address}" if address else ""
    phone_str = f"📞 {phone}" if phone else ""

    openers = [
        f"{brand}，诚邀你的加入。{desc}",
        f"如果你也在寻找志同道合的伙伴，{brand}欢迎你。",
        f"一个人可以走得很快，但一群人可以走得更远。{brand}，等你来。",
        f"你知道吗？{brand}正在招募新会员。",
    ]
    opener = random.choice(openers)

    middles = [
        "我们相信，独行快，众行远。在这里，你可以结识志同道合的伙伴，获取行业前沿资讯，共享资源、共同成长。",
        "在这里，每一次交流都可能是一次新的启发。人脉、资源、资讯——我们帮你一站式打通。",
        "不只是会员，更是伙伴。不只是加入，更是成长。",
    ]
    middle = random.choice(middles)

    closers = [
        f"{phone_str}期待与你同行。",
        f"名额有限，先到先得。{phone_str}",
        f"加入我们，一起做点有意义的事。{phone_str}",
    ]
    closer = random.choice(closers)

    voiceover = f"{opener}。{middle} {closer}"

    scene_texts = {
        "s1": {"line1": "诚邀加入", "line2": brand, "sub": desc or "携手共进 · 共创未来"},
        "s2": {"line1": "为什么加入", "line2": "汇聚行业精英 · 共享前沿资源", "sub": "连接 · 赋能 · 共创"},
        "s3": {"line1": "你能获得", "line2": "人脉资源 · 行业资讯 · 培训赋能", "sub": "不止是会员，更是伙伴"},
        "s4": {"line1": "入会条件", "line2": "热爱互联网事业 · 认可协会理念", "sub": "欢迎各类企业和个人加入"},
        "s5": {"price": "立即申请", "info": f"{address_str}\n{phone_str}" if phone_str else address_str, "limit": "名额有限"},
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_product(name, desc, value, price, phone):
    """产品种草模板文案生成（升级版）"""
    desc = desc or ""
    value = value or ""
    import random

    phone_str = f"📞 {phone}" if phone else ""
    price_str = price if price else "限时优惠"

    # 解析卖点
    points = [p.strip() for p in value.split("、") if p.strip()]
    p1 = points[0] if len(points) > 0 else "品质保证"
    p2 = points[1] if len(points) > 1 else "价格实惠"
    p3 = points[2] if len(points) > 2 else "口碑推荐"

    # ── 多样化的痛点开场 ──
    pain_openers = [
        f"你是不是也有这样的烦恼？{desc}。",
        f"还在为{desc or '选不到好产品'}发愁？",
        f"说实话，{desc or '找到一款合适的产品'}，真的没那么难。",
        f"你踩过{desc or '选品'}的坑吗？这次，帮你一次解决。",
    ]
    pain_opener = random.choice(pain_openers)

    # ── 多样化的行动号召 ──
    cta_variants = [
        f"现在下单{price_str}，机会难得，别错过了。",
        f"{price_str}，给自己一个试试的机会。",
        f"别犹豫了，{price_str}，用过你就知道值了。",
        f"{price_str}，早买早享受。",
    ]
    cta = random.choice(cta_variants)

    # ── 加分金句 ──
    product_phrases = [
        "选对了，生活品质提升一大截。",
        "好东西，值得早一点拥有。",
        "买对不买贵，选对才省心。",
        "用过之后，你就回不去了。",
    ]
    product_phrase = random.choice(product_phrases)

    desc_part = f"，{desc}" if desc else ""
    voiceover = (
        f"{pain_opener}"
        f"其实，选对东西，问题就解决了一半。"
        f"{name}，{desc or '值得你试试'}。"
        f"{p1}，{p2}，{p3}。"
        f"{product_phrase}"
        f"{cta}"
    )

    scene_texts = {
        "s1": {"line1": "你是不是也遇到过", "line2": desc or "选不到好产品", "sub": "其实，解决办法很简单"},
        "s2": {"line1": "直到遇见它", "line2": name, "line3": desc or "品质之选"},
        "s3": {"line1": "三大理由", "line2": p1, "line3": p2, "line4": p3},
        "s4": {"price": price_str, "cta": "立即购买", "info": phone_str}
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_ip(name, tags, phone, value):
    """个人IP模板文案生成（升级版）"""
    tags = tags or ""
    value = value or ""
    import random

    phone_str = f"📞 {phone}" if phone else ""

    # ── 多样化的开场 ──
    openers = [
        f"你好，我是{name}。",
        f"我是{name}，{tags or '一个普通的追梦人'}。",
        f"很多人问我，{name}是谁？今天就正式认识一下。",
        f"你可能不知道{name}，但如果你有{value or '这方面的需求'}，我们很有缘。",
        f"认识一下，我是{name}。",
    ]
    opener = random.choice(openers)

    if value:
        value_part = f"我专注{value}。"
        # 更自然的表达
        help_part = f"如果你有{value}方面的需求，我刚好可以帮你。"
    else:
        value_part = ""
        help_part = "如果你有这方面的需求，欢迎随时找我。"

    closers = [
        f"期待与你连接。{' ' + phone_str if phone_str else ''}",
        f"随时欢迎交流。{' ' + phone_str if phone_str else ''}",
        f"希望我的经验，能为你带来一些价值。",
        f"你的信任，就是我做这件事最大的动力。",
    ]
    closer = random.choice(closers)

    voiceover = f"{opener} {tags}。{value_part}{help_part}{closer}"

    help_items = value.split("、")
    h1 = help_items[0] if len(help_items) > 0 else "专业服务"
    h2 = help_items[1] if len(help_items) > 1 else "经验分享"
    h3 = help_items[2] if len(help_items) > 2 else "资源对接"

    scene_texts = {
        "s1": {"title": "我是谁", "name": name, "tag": tags or "行业专家", "sub": f"专注{value or '专业领域'} · 实战派"},
        "s2": {"line1": "我能帮你", "line2": h1, "line3": h2, "line4": h3},
        "s3": {"line1": "怎么找到我", "phone": phone_str or "期待与你连接", "sub": "期待与你连接"}
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_food(brand, desc, phone, address):
    """餐饮模板文案生成（升级版：5种以上句式结构 + 情感化表达）"""
    desc = desc or ""
    import random

    address_str = f"📍 {address}" if address else "📍 文山"
    phone_str = f"📞 {phone}" if phone else ""

    # ── 情感化开场句库（替代固定"在文山"） ──
    openers = [
        f"你可知道，在{address or '文山'}，藏着这么一家店——",
        f"今天要讲的，是{address or '文山'}一家{brand}的故事。",
        f"说实话，第一次走进{brand}的时候，我就知道来对了。",
        f"在{address or '文山'}，提到{desc or '好吃的'}，很多人第一个想到的就是{brand}。",
        f"你问我在{address or '文山'}去哪吃？那我必须说{brand}。",
        f"有人说，好的味道都藏在巷子里。比如{brand}，就在{address or '文山'}。",
        f"{brand}？那可是{address or '文山'}的老朋友了。",
        f"如果让我推荐{address or '文山'}的美食，{brand}一定排在前三。",
    ]

    # ── 卖点角度多样性 ──
    if "年" in desc:
        s1_line1 = "做了这么多年"
        s4_story = ["从当初开始", "一直做到现在", "靠的是坚持", "和一份用心"]
        hook = f"一干就是这么多年，靠的是什么？其实也没什么特别的，就是不想辜负每个来吃饭的人。"
    elif "新鲜" in desc or "食材" in desc or "原料" in desc:
        s1_line1 = "真材实料"
        s4_story = ["选最好的料", "花最多的心", "没有什么窍门", "就是不肯将就"]
        hook = f"选材这件事，老板从来不肯将就。用他的话说：'食材不好，手艺再好也白搭。'"
    elif any(w in desc for w in ["老", "传承", "字号", "招牌"]):
        s1_line1 = "老店不老"
        s4_story = ["从父辈开始", "传到这一代", "守的不只是店", "是一份信任"]
        hook = f"有人问，为什么能开这么多年？答案很简单——把客人当家人，把味道当家味。"
    elif any(w in desc for w in ["便宜", "实惠", "性价比"]):
        s1_line1 = "实在人"
        s4_story = ["不搞虚的", "不玩套路", "把价格做实在", "把味道做正宗"]
        hook = f"老板是个实在人，不搞花里胡哨的。价格实在，分量实在，味道更实在。"
    elif any(w in desc for w in ["火锅","串串","麻辣","辣","烧烤","烤"]):
        s1_line1 = "就是这个味"
        s4_story = ["从第一口开始", "就停不下来", "不是有多特别", "就是够地道"]
        hook = f"你要问到底有多好吃？我只能说——吃过的，没有不回头找的。"
    else:
        s1_line1 = "用心做菜"
        s4_story = ["从零开始", "一路坚持", "没有捷径", "用心就好"]
        hook = f"做餐饮这件事，说难不难，说简单也不简单。秘诀？就是把每一天该做的事做好。"

    desc_part = f"，{desc}" if desc else ""
    opener = random.choice(openers)

    # ── 金句收尾 ──
    closers = [
        "好的味道，从来不会辜负每一个认真生活的人。",
        "生活再忙，也要好好吃饭。",
        "别犹豫了，你的味蕾会感谢你的。",
        "来都来了，不吃一顿再走？",
        "说什么都不如亲自来尝一口。",
    ]
    closer = random.choice(closers)

    voiceover = (
        f"{opener}"
        f"{desc_part}。"
        f"{hook}"
        f"食材新鲜，味道地道，价格公道——这就是{brand}的底气。"
        f"{closer}"
        f"{' ' + phone_str if phone_str else ''}"
    )

    # 场景文案也多样化
    scene_s2_variants = [
        {"line1": brand, "line2": desc or "招牌好味道", "line3": "吃过的都成了回头客", "sub": "口碑，是最好的广告"},
        {"line1": brand, "line2": desc or "来过的都说好", "line3": "每一口都是诚意", "sub": f"在{address or '文山'} · 必吃榜"},
        {"line1": brand, "line2": desc or "匠心出品", "line3": "老顾客吃了都说好", "sub": "味道不会骗人"},
    ]
    s2 = random.choice(scene_s2_variants)

    scene_s3_variants = [
        {"line1": "真材实料", "line2": "良心出品", "sub": "做餐饮，先过自己这一关"},
        {"line1": "每一道工序", "line2": "都用心对待", "sub": "匠心 · 良心 · 初心"},
        {"line1": "从选材到上桌", "line2": "每一步都不将就", "sub": "品质，是立店之本"},
    ]
    s3 = random.choice(scene_s3_variants)

    scene_texts = {
        "s1": {"line1": s1_line1, "line2": brand, "sub": f"在{address or '文山'} · {desc or '每一口都是诚意'}"},
        "s2": s2,
        "s3": s3,
        "s4": {"line1": s4_story[0], "line2": s4_story[1], "line3": s4_story[2], "line4": s4_story[3], "sub": "匠心 · 良心 · 初心"},
        "s5": {"price": "限时特惠", "info": "进店消费即享优惠\n活动进行中", "limit": "错过等明年"},
        "s6": {"line1": "欢迎你来坐坐", "address": address_str, "phone_str": phone_str if phone_str else "", "sub": "用心做菜 · 等你来尝"},
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_event(brand, desc, phone, address):
    """活动邀约模板文案生成（升级版：句式多样 + 情感化）"""
    desc = desc or ""
    import random

    address_str = f"📍 {address}" if address else ""
    phone_str = f"📞 {phone}" if phone else ""
    desc_part = f"，{desc}" if desc else ""

    # 根据关键词选择文案角度
    if any(w in desc for w in ["培训","课程","学习","讲座","AI","实战"]):
        tagline = "学到就是赚到"
        cta = "位置不多了"
        title = f"{desc or 'AI实战课'}"
        openers = [
            f"想提升自己？{brand}的{desc or '课程'}，真的值得来一趟。",
            f"说实话，能让你真正学以致用的{desc or '课程'}，不多了。{brand}算一个。",
            f"你有多久没有系统学习了？{brand}准备了一场{desc or '分享'}，干货满满。",
        ]
    elif any(w in desc for w in ["开业","开张","新店"]):
        tagline = "新店开张"
        cta = "开业特惠"
        title = brand
        openers = [
            f"好消息！{brand}开业啦！🎉",
            f"{address or '文山'}的朋友们，{brand}正式开业了！",
            f"盼了好久，{brand}终于要和大家见面了。",
        ]
    elif any(w in desc for w in ["促销","打折","优惠","周年"]):
        tagline = "一年一次"
        cta = "错过等明年"
        title = f"{desc or brand}"
        openers = [
            f"一年一次的{brand}大促，终于来了。",
            f"等了一整年，{brand}的优惠活动终于开始了。",
            f"说真的，这个价格平时想都不敢想。",
        ]
    elif any(w in desc for w in ["沙龙","茶话会","交流","聚会"]):
        tagline = "以茶会友"
        cta = "名额有限"
        title = brand
        openers = [
            f"一杯茶，一群人，一个下午。{brand}沙龙，期待你的到来。",
            f"你喜欢交流吗？来{brand}坐坐，和有趣的人聊聊天。",
            f"这不仅仅是一场沙龙，更是一次高质量的社交。",
        ]
    else:
        tagline = "邀请函"
        cta = "期待你的到来"
        title = brand
        openers = [
            f"你好，这里有一份来自{brand}的邀请函。",
            f"我们准备了一场特别的活动，想邀请你参加。",
            f"{brand}，诚邀你的莅临。",
        ]

    opener = random.choice(openers)

    closers = [
        "名额有限，先到先得。我们在现场等你。",
        "来都来了，总得带走点什么。这次，别错过了。",
        "说真的，错过这次，可能真的要再等一年。",
        "期待在现场见到你。",
        "别犹豫了，现在就行动吧。",
    ]
    closer = random.choice(closers)

    voiceover = (
        f"{opener}{desc_part}。"
        f"我们准备了很多干货和惊喜，就是想让来的每个人不虚此行。"
        f"{closer}"
        f"{' ' + phone_str if phone_str else ''}"
    )

    scene_texts = {
        "s1": {"line1": tagline, "line2": title, "sub": desc or f"{brand}邀请你来参加"},
        "s2": {"line1": "谁来分享", "tags": "行业专家 · 实战派\n干货满满", "sub": "只讲真东西"},
        "s3": {"line1": "有什么收获", "line2": f"{desc or '干货分享'}", "sub": "来了就有收获"},
        "s4": {"line1": "名额有限", "price": cta, "info": (f"{address_str}\n{phone_str}" if phone_str else address_str) or "", "limit": "立即报名"},
        "s5": {},
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_store(brand, desc, phone, address):
    """实体店推广模板文案生成（升级版）"""
    desc = desc or ""
    import random

    address_str = f"📍 {address}" if address else ""
    phone_str = f"📞 {phone}" if phone else ""
    desc_part = f"，{desc}" if desc else ""

    # ── 多样化的开场 ──
    openers = [
        f"在{address or '文山'}，有一家店叫{brand}。{desc_part}。",
        f"如果你在{address or '文山'}，你一定会路过{brand}。",
        f"说起{address or '文山'}的{desc or '服务'}，很多人第一个想到的就是{brand}。",
        f"朋友推荐了{brand}，说真的，去过一次就知道为什么了。",
        f"{brand}？{address or '文山'}的老顾客都懂的。",
    ]
    opener = random.choice(openers)

    # ── 中间段多样性 ──
    middles = [
        "做服务这件事，没有别的窍门，就是用心做好每一件小事。",
        "专业不是嘴上说说，是每一个细节都能感受到的。",
        "把每一件小事做好，就是对顾客最大的尊重。",
        "没有什么惊天动地的故事，就是日复一日的坚持。",
    ]
    middle = random.choice(middles)

    closers = [
        f"如果你也想感受这份用心，欢迎来坐坐。{phone_str}",
        f"你的信任，就是我们最大的动力。{phone_str}",
        f"好的服务，值得你亲自来体验。{phone_str}",
        f"我们在{address or '文山'}等你。{phone_str}",
    ]
    closer = random.choice(closers)

    voiceover = (
        f"{opener}"
        f"{middle}"
        f"{closer}"
    )

    scene_s1_variants = [
        {"line1": brand, "line2": desc or "用心服务", "sub": address_str or "欢迎光临"},
        {"line1": brand, "line2": desc or "你的选择，我的坚持", "sub": address_str or "欢迎你来"},
        {"line1": brand, "line2": desc or "值得信赖", "sub": address_str or "专业 · 用心 · 靠谱"},
    ]
    s1 = random.choice(scene_s1_variants)

    scene_texts = {
        "s1": s1,
        "s2": {"line1": "专业 · 用心 · 值得信赖", "line2": desc or "你的选择，我的坚持"},
        "s3": {"line1": "为什么选择我们", "sub": "专业团队 · 贴心服务 · 口碑之选"},
        "s4": {"line1": address_str or f"📍 {address or '文山'}", "phone_str": phone_str, "sub": "等你来"}
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_farm(brand, desc, price, phone):
    """农产品带货模板文案生成（升级版）"""
    desc = desc or ""
    import random

    price_str = price or ""
    phone_str = f"📞 {phone}" if phone else ""

    # ── 多样化的开场 ──
    openers = [
        f"好东西，来自好产地。{brand}{':' + desc if desc else ''}",
        f"你有多久没吃到{desc or '小时候的味道'}了？{brand}帮你找到了。",
        f"今天要给你安利一款好东西——来自{brand}的{desc or '原产地好物'}。",
        f"如果你也喜欢{desc or '原生态的味道'}，那你一定会爱上{brand}。",
        f"从{desc or '山野'}到你家，{brand}把最好的都带来了。",
    ]
    opener = random.choice(openers)

    # ── 中间段多样性 ──
    middles = [
        "自然生长，用心守护，每一份都是大自然的馈赠。",
        "不打农药不催熟，时间酿出的甜，是任何添加剂都比不了的。",
        "从田间到餐桌，每一步我们都亲自盯着，品质这件事，不敢马虎。",
        "好山好水出好物，这里的每一寸土地都在告诉你——什么才是真正的原生态。",
    ]
    middle = random.choice(middles)

    closers = [
        f"{price_str}，健康不贵。想尝尝这份来自原产地的味道？{phone_str}",
        f"想尝尝？{price_str}。{phone_str}",
        f"{price_str}，给自己的餐桌加点大自然的味道。{phone_str}",
        f"好东西不等人，{price_str}。{phone_str}",
    ]
    closer = random.choice(closers)

    voiceover = (
        f"{opener}"
        f"{middle}"
        f"{closer}"
    )

    scene_texts = {
        "s1": {"line1": "原产地 · 好产品", "line2": brand, "sub": desc or "自然馈赠·品质之选"},
        "s2": {"line1": brand, "line2": desc or "好产品来自好产地", "sub": "每一份都经得起检验"},
        "s3": {"line1": "三大优势", "line2": "原产地直供 · 品质保障 · 价格实在", "sub": "吃得更放心"},
        "s4": {"price": price_str or "点击询价", "cta": "立即购买", "info": phone_str}
    }
    return {"scene_texts": scene_texts, "voiceover_text": voiceover}


def _gen_copy_variants(template_id: str, brand: str, desc: str, address: str, phone: str, value: str, price: str) -> list:
    """生成3版不同风格的文案"""
    variants = []

    if template_id in ('food_promo', 'food_promo_v2'):
        # 餐饮模板3版
        v1 = {
            "style": "走心叙事风",
            "scenes": [
                {"text": f"在{address or '文山'}，有家店一做就是很多年"},
                {"text": f"{brand}，{desc or '用心做好每一道菜'}"},
                {"text": "从选材到出锅，每一步都不将就"},
                {"text": f"地址：{address or '文山'} 📞 {phone or ''}"}
            ],
            "voiceover": f"在{address or '文山'}，有这样一家店。{brand}，{desc or '用心做好每一道菜'}。从选材到出锅，每一步都不将就。欢迎你来坐坐。"
        }
        v2 = {
            "style": "简单直接风",
            "scenes": [
                {"text": f"来{brand}，吃好的"},
                {"text": desc or '食材新鲜·味道正宗'},
                {"text": f"📍 {address or '文山'}"},
                {"text": f"想吃好的，就来{brand}"}
            ],
            "voiceover": f"{brand}，{desc or '食材新鲜·味道正宗'}。就在{address or '文山'}，等你来吃。"
        }
        v3 = {
            "style": "促进行动风",
            "scenes": [
                {"text": f"文山人，都去{brand}吃了"},
                {"text": desc or '好吃不贵·回头客多'},
                {"text": f"现在就去📍{address or '文山'}"},
                {"text": f"赶快约起来！📞 {phone or ''}"}
            ],
            "voiceover": f"要做就做最好，要吃就来{brand}。{desc or '好吃不贵·回头客多'}。地址在{address or '文山'}，{phone or ''}。"
        }
        variants = [v1, v2, v3]

    elif template_id in ('personal_ip', 'personal_ip_v1'):
        v1 = {
            "style": "专业权威风",
            "scenes": [
                {"text": f"你好，我是{brand}"},
                {"text": desc or '专注领域，深耕多年'},
                {"text": value or '我能帮你解决问题'},
                {"text": f"联系我：{phone or ''}"}
            ],
            "voiceover": f"你好，我是{brand}。{desc or '专注领域，深耕多年'}。{value or '我能帮你解决问题'}。期待与你交流。"
        }
        v2 = {
            "style": "亲和信任风",
            "scenes": [
                {"text": f"认识一下，{brand}"},
                {"text": desc or '用专业帮你少走弯路'},
                {"text": value or '我的价值就是帮你成事'},
                {"text": f"随时找我：{phone or ''}"}
            ],
            "voiceover": f"认识一下，我是{brand}。{desc or '用专业帮你少走弯路'}。{value or '我的价值就是帮你成事'}。随时联系我。"
        }
        v3 = {
            "style": "痛点引动风",
            "scenes": [
                {"text": "你是不是也有这样的困扰？"},
                {"text": f"我是{brand}，{desc or '专注解决这个问题'}"},
                {"text": value or '我用专业帮你搞定'},
                {"text": f"别等了，找我聊聊。{phone or ''}"}
            ],
            "voiceover": f"你是不是也有这样的困扰？我是{brand}，{desc or '专注解决这个问题'}。{value or '我用专业帮你搞定'}。"
        }
        variants = [v1, v2, v3]

    elif template_id in ('product_seed', 'product_seed_v1'):
        v1 = {
            "style": "痛点解决风",
            "scenes": [
                {"text": f"你还在为这个问题烦恼吗？"},
                {"text": f"{brand}，{desc or '解决你的核心痛点'}"},
                {"text": value or '三大优势·品质保障'},
                {"text": f"只要{price or '实惠价'} 📞 {phone or ''}"}
            ],
            "voiceover": f"还在为这个问题烦恼？{brand}，{desc or '解决你的核心痛点'}。{value or '三大优势·品质保障'}。只要{price or '实惠价'}。"
        }
        v2 = {
            "style": "品质种草风",
            "scenes": [
                {"text": f"好东西，值得分享"},
                {"text": f"{brand} — {desc or '用过都说好'}"},
                {"text": value or '质量杠杠的'},
                {"text": f"{price or '限时价'} 📞 {phone or ''}"}
            ],
            "voiceover": f"好东西值得分享。{brand}，{desc or '用过都说好'}。{value or '质量杠杠的'}。现在只要{price or '实惠价'}。"
        }
        v3 = {
            "style": "限时促单风",
            "scenes": [
                {"text": f"手慢无！{brand}"},
                {"text": desc or '限时特惠·错过等一年'},
                {"text": f"仅需{price or '惊爆价'}"},
                {"text": f"扫码/来电：{phone or ''}"}
            ],
            "voiceover": f"手慢无！{brand}，{desc or '限时特惠·错过等一年'}。仅需{price or '惊爆价'}！赶快联系:{phone or ''}。"
        }
        variants = [v1, v2, v3]

    elif template_id == 'event_invite':
        v1 = {
            "style": "正式邀请风",
            "scenes": [
                {"text": f"【邀请函】{brand}"},
                {"text": desc or '诚邀您的参与'},
                {"text": f"📍 {address or ''}"},
                {"text": f"期待您的光临 📞 {phone or ''}"}
            ],
            "voiceover": f"诚挚邀请您参加{brand}。{desc or '诚邀您的参与'}。地点在{address or ''}。期待您的光临！"
        }
        v2 = {
            "style": "热闹氛围风",
            "scenes": [
                {"text": f"🎉 {brand}，来就对了！"},
                {"text": desc or '精彩活动·不容错过'},
                {"text": f"📍 {address or ''}"},
                {"text": f"现在就报名 📞 {phone or ''}"}
            ],
            "voiceover": f"{brand}来了！{desc or '精彩活动·不容错过'}。就在{address or ''}。现在报名联系{phone or ''}。"
        }
        v3 = {
            "style": "稀缺限位风",
            "scenes": [
                {"text": f"名额有限！{brand}"},
                {"text": desc or '仅限XX席·先到先得'},
                {"text": f"📍 {address or ''}"},
                {"text": f"马上锁定席位 📞 {phone or ''}"}
            ],
            "voiceover": f"名额有限！{brand}，{desc or '仅限XX席·先到先得'}。地点{address or ''}。马上联系{phone or ''}锁定席位。"
        }
        variants = [v1, v2, v3]

    elif template_id in ('sanqi_industry',):
        v1 = {
            "style": "自然品质风",
            "scenes": [
                {"text": f"道地三七，来自{brand}"},
                {"text": desc or '天然种植·品质保障'},
                {"text": "源自文山，自然馈赠"},
                {"text": f"📞 {phone or ''} | {address or '文山'}"}
            ],
            "voiceover": f"道地三七，来自{brand}。{desc or '天然种植·品质保障'}。源自文山，自然馈赠。联系{phone or ''}了解更多。"
        }
        v2 = {
            "style": "产业专业风",
            "scenes": [
                {"text": f"{brand} — 专注三七产业"},
                {"text": desc or '二十年深耕·品质如一'},
                {"text": "从种植到加工，全程品控"},
                {"text": f"合作洽谈：{phone or ''}"}
            ],
            "voiceover": f"{brand}专注三七产业。{desc or '二十年深耕·品质如一'}。从种植到加工全程品控。合作联系{phone or ''}。"
        }
        v3 = {
            "style": "健康价值风",
            "scenes": [
                {"text": f"三七好，才是真的好"},
                {"text": f"{brand}，{desc or '健康之选'}"},
                {"text": "每天一小勺，健康大不同"},
                {"text": f"立即订购：{phone or ''}"}
            ],
            "voiceover": f"三七好，才是真的好。{brand}，{desc or '健康之选'}。每天一小勺，健康大不同。立即订购{phone or ''}。"
        }
        variants = [v1, v2, v3]

    elif template_id == 'association_invite':
        v1 = {
            "style": "庄重邀请风",
            "scenes": [
                {"text": f"诚邀加入{brand}"},
                {"text": desc or '汇聚行业精英·共享前沿资源'},
                {"text": "携手同行，共创未来"},
                {"text": f"入会咨询：{phone or ''} | {address or ''}"}
            ],
            "voiceover": f"诚邀您加入{brand}。{desc or '汇聚行业精英·共享前沿资源'}。携手同行，共创未来。入会咨询{phone or ''}。"
        }
        v2 = {
            "style": "合作共赢风",
            "scenes": [
                {"text": f"一个人走得快，一群人走得远"},
                {"text": f"来{brand}，和大家一起"},
                {"text": desc or '资源·人脉·成长'},
                {"text": f"加入我们：{phone or ''}"}
            ],
            "voiceover": f"一个人走得快，一群人走得远。来{brand}，和大家一起。{desc or '资源·人脉·成长'}。加入我们{phone or ''}。"
        }
        v3 = {
            "style": "价值吸引风",
            "scenes": [
                {"text": f"你在找组织？{brand}等你"},
                {"text": desc or '行业前沿·实战赋能'},
                {"text": "会员专属资源·全年活动"},
                {"text": f"立即加入：{phone or ''}"}
            ],
            "voiceover": f"你在找组织？{brand}等你。{desc or '行业前沿·实战赋能'}。会员专属资源，全年活动不断。立即加入{phone or ''}。"
        }
        variants = [v1, v2, v3]

    else:
        # 通用模板
        v1 = {
            "style": "正式风格",
            "scenes": [
                {"text": brand or "标题"},
                {"text": desc or '详细内容'},
                {"text": address or ''},
                {"text": f"联系：{phone or ''}"}
            ],
            "voiceover": f"{brand}。{desc or ''}。{'地址：' + address if address else ''}。联系方式：{phone or ''}。"
        }
        v2 = {
            "style": "简洁风格",
            "scenes": [
                {"text": brand or "标题"},
                {"text": desc or '一句话说明'},
                {"text": phone or ''},
                {"text": "等你来"}
            ],
            "voiceover": f"{brand}。{desc or ''}。联系方式：{phone or ''}。"
        }
        v3 = {
            "style": "行动号召风",
            "scenes": [
                {"text": f"注意！{brand or '活动'}来了"},
                {"text": desc or '别错过好机会'},
                {"text": f"现在就行动"},
                {"text": phone or ''}
            ],
            "voiceover": f"注意！{brand or '活动'}来了。{desc or '别错过好机会'}。现在就行动！联系{phone or ''}。"
        }
        variants = [v1, v2, v3]

    return variants


def _get_font_size_for_style(style: str, el: dict) -> int:
    """根据样式名返回Canvas渲染字体大小"""
    size_map = {
        "large_gold": 48,
        "large_white": 44,
        "large_cyan": 36,
        "info": 28,
        "limit": 32,
        "phone": 32,
        "subtitle": 22,
        "price": 48,
    }
    # 优先使用元素上定义的size
    raw_size = el.get("size")
    if isinstance(raw_size, (int, float)):
        return int(raw_size)
    return size_map.get(style, 32)


def _get_color_for_style(style: str, colors: dict) -> str:
    """根据样式名返回颜色"""
    color_map = {
        "large_gold": colors.get("gold_text", "#ffd54f"),
        "large_white": colors.get("white_text", "#ffffff"),
        "large_cyan": colors.get("cyan_text", "#00d4ff"),
        "info": colors.get("white_text", "#ffffff"),
        "limit": colors.get("gold_text", "#ffd54f"),
        "phone": colors.get("gold_text", "#ffd54f"),
        "subtitle": colors.get("subtitle_color", "rgba(255,255,255,0.4)"),
        "price": colors.get("gold_text", "#ffd54f"),
    }
    return color_map.get(style, colors.get("white_text", "#ffffff"))


# ===================== C任务：一句话出片 =====================

# 自然语言关键词→模板匹配表
TEMPLATE_KEYWORDS = {
    "food_promo": ["餐饮", "饭店", "火锅", "烧烤", "米粉", "面馆", "小吃", "餐厅", "食堂", "外卖", "吃", "饭", "菜", "美食", "吃货", "吃货", "推广", "招牌"],
    "store_promo": ["美发", "理发", "美容", "健身", "家政", "按摩", "修理", "维修", "洗衣", "干洗", "店铺", "店主"],
    "event_invite": ["活动", "邀请", "聚会", "派对", "沙龙", "会议", "讲座", "培训", "开张", "开业", "发布会"],
    "personal_ip": ["个人IP", "我是", "介绍", "个人品牌", "专家", "老师", "顾问", "教练", "创始人", "CEO"],
    "product_seed": ["产品", "种草", "带货", "推荐", "安利", "卖", "好物", "神器", "干货", "实用"],
    "farm_promo": ["农产品", "三七", "茶叶", "水果", "蔬菜", "蜂蜜", "野生", "农家", "土特产", "原产地", "有机"],
    "sanqi_industry": ["三七", "文山三七", "药材", "养生", "滋补", "保健品"],
    "association_invite": ["协会", "商会", "会员", "加入", "组织", "联盟", "社团"],
    "xinxue_course": ["心学", "阳明", "课程", "培训", "学习", "教育", "线上课"],
    "xiaohongshu_style": ["小红书", "种草", "知识", "分享", "打卡", "推荐"],
}

def _smart_match_template(user_text: str) -> tuple:
    """根据用户一句话智能匹配模板，返回 (template_id, brand, desc)"""
    user_text = user_text.strip()
    if not user_text:
        return "food_promo", "", ""

    # 模板匹配打分（加权）
    scores = {}
    weights = {
        "personal_ip": 3,    # "我是"等专有匹配权重大
        "sanqi_industry": 2,
        "farm_promo": 2,
        "store_promo": 2,
        "food_promo": 1,
        "event_invite": 1,
        "product_seed": 1,
        "association_invite": 1,
        "xinxue_course": 1,
        "xiaohongshu_style": 1,
    }
    for tid, keywords in TEMPLATE_KEYWORDS.items():
        score = sum(weights.get(tid, 1) for kw in keywords if kw in user_text)
        if score > 0:
            scores[tid] = score

    # 最高分的模板
    best_tid = "food_promo"
    best_score = 0
    for tid, score in scores.items():
        if score > best_score:
            best_score = score
            best_tid = tid

    # 从文本中提取品牌名
    brand = user_text
    # 去掉常见前缀
    for prefix in ["我是", "我叫", "我们", "帮我做一条", "帮我", "做一条", "我要做", "帮我家", "帮我家的", "我们家的"]:
        if prefix in user_text:
            after = user_text[user_text.index(prefix) + len(prefix):].strip()
            if after and len(after) < len(brand):
                brand = after
    # 去掉第一个"的"之后的内容（保持"老张火锅店"这样的完整）
    import re
    # 对于"的xxx"结构，"的"之前的完整词组保留
    parts = re.split(r'的(?!.*的)', brand, maxsplit=1)
    if len(parts) > 1 and len(parts[0]) >= 2:
        brand = parts[0]
    # 取前10字
    brand = brand[:10]
    # 去掉逗号
    brand = brand.replace("，", "").replace(",", "").strip()

    return best_tid, brand, user_text


QUEUE = []                # 待渲染任务列表 [(job_id, template_path, config)]
MAX_CONCURRENT = 4        # 最多同时渲染4个
QUEUE_LOCK = threading.Lock()

def queue_render(job_id, template_path, config):
    """将任务加入渲染队列"""
    with QUEUE_LOCK:
        JOBS[job_id]["status"] = "queued"
        QUEUE.append((job_id, template_path, config))
    # 尝试触发队列处理
    t = threading.Thread(target=process_queue, daemon=True)
    t.start()

def process_queue():
    """从队列取任务执行，不超过MAX_CONCURRENT并发"""
    # 统计当前正在渲染的任务数
    running = sum(1 for j in JOBS.values() if j.get("status") == "running")
    with QUEUE_LOCK:
        while QUEUE and running < MAX_CONCURRENT:
            job_id, template_path, config = QUEUE.pop(0)
            JOBS[job_id]["status"] = "running"
            running += 1
            t = threading.Thread(target=render_video, args=(template_path, config, job_id), daemon=True)
            t.start()


def init_routes(app):
    """注册所有视频相关路由"""

    @app.route("/api/queue-status")
    def api_queue_status():
        with QUEUE_LOCK:
            queued = sum(1 for j in JOBS.values() if j.get("status") == "queued")
            running = sum(1 for j in JOBS.values() if j.get("status") == "running")
            completed = sum(1 for j in JOBS.values() if j.get("status") == "completed")
            failed = sum(1 for j in JOBS.values() if j.get("status") == "failed")
        return jsonify({"queued": queued, "running": running, "completed": completed, "failed": failed})

    @app.route("/api/generate-copy", methods=["POST"])
    def api_generate_copy():
        """
        AI自动生成文案+配音词，然后渲染视频
        用户只需提供：brand（店名）、description（一句话描述）、template_id
        """
        data = request.json or {}
        template_id = data.get("template_id", "")
        brand = data.get("brand", "").strip()
        desc = data.get("description", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        value = data.get("value", "").strip()
        price = data.get("price", "").strip()
        variant = data.get("variant", "").strip()

        if not brand:
            return jsonify({"error": "请填写店名/品牌名"}), 400

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 400

        # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
        copy_data = _llm_copy_with_fallback(template_id, brand, desc, address, phone, value=value, price=price)

        # 应用变体微调
        if variant:
            copy_data = _apply_variant_to_copy(copy_data, template_id, variant)

        # 构建渲染参数
        text_config = copy_data["scene_texts"]
        vo_text = copy_data["voiceover_text"]

        # 获取变体配色
        colors_scheme = template["config"].get("colors", {}).get("scheme", "warm_dark")
        if variant:
            tpl_var = TEMPLATE_VARIANTS.get(template_id)
            if tpl_var:
                var_data = tpl_var["variants"].get(variant)
                if var_data:
                    colors_scheme = var_data["colors"]["primary"]

        params = {
            "animation": template["config"].get("animation", {}).get("style", "standard"),
            "bg_type": template["config"].get("background", {}).get("type", "gradient"),
            "quality": "standard",
            "voiceover": {
                "enabled": True,
                "voice": template["config"].get("audio", {}).get("voiceover", {}).get("default_voice", "zh-CN-YunyangNeural"),
                "text": vo_text
            },
            "subtitles": {"enabled": True},
            "bgm": {"enabled": True, "file": "uplifting"}
        }

        merged = merge_config_with_user(template["config"], params, is_preview=False)
        job_id = str(uuid.uuid4())[:8]
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        JOBS[job_id] = {"status": "rendering", "progress": 0, "output": None, "error": None, "brand": brand, "template_id": tid, "user_phone": req_user_phone, "_created": time.time()}
        jobs_save(job_id)

        thread = threading.Thread(target=render_video,
                                  args=(Path(template["path"]), merged, job_id))
        thread.start()

        return jsonify({
            "job_id": job_id,
            "status": "started",
            "copy_preview": {
                "scenes": text_config,
                "voiceover": vo_text[:100] + "..."
            }
        })

    @app.route("/api/batch-generate", methods=["POST"])
    def api_batch_generate():
        """批量生成：接收多个params配置，依次排队生成"""
        data = request.json or {}
        template_id = data.get("template_id", "")
        batch_params = data.get("batch_params", [])

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 400

        batch_id = str(uuid.uuid4())[:8]
        job_ids = []
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        for i, params in enumerate(batch_params):
            merged = merge_config_with_user(template["config"], params, is_preview=False)
            jid = f"{batch_id}_{i}"
            JOBS[jid] = {"status": "queued", "progress": 0, "output": None, "error": None, "_created": time.time(), "user_phone": req_user_phone}
            jobs_save(jid)
            job_ids.append(jid)
            BATCH_QUEUE.append((jid, template_id, merged))

        # 启动队列处理线程
        if len(BATCH_QUEUE) == len(job_ids):  # 第一次添加，启动处理器
            def process_queue():
                import time
                while BATCH_QUEUE:
                    jid, tid, merged = BATCH_QUEUE.pop(0)
                    JOBS[jid]["status"] = "rendering"
                    jobs_save(jid)
                    tmpl = _get_template(tid)
                    if tmpl:
                        render_video(Path(tmpl["path"]), merged, jid)
                    time.sleep(1)
            t = threading.Thread(target=process_queue)
            t.start()

        return jsonify({"batch_id": batch_id, "job_ids": job_ids, "status": "queued"})

    @app.route("/api/preview", methods=["POST"])
    def api_preview():
        data = request.json or {}
        template_id = data.get("template_id", "")
        user_params = data.get("params", {})

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 400

        merged = merge_config_with_user(template["config"], user_params, is_preview=True)

        job_id = str(uuid.uuid4())[:8]
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        JOBS[job_id] = {"status": "rendering", "progress": 0, "output": None, "error": None, "brand": "", "template_id": template_id, "user_phone": req_user_phone, "_created": time.time()}
        jobs_save(job_id)

        thread = threading.Thread(target=render_video,
                                  args=(Path(template["path"]), merged, job_id))
        thread.start()

        return jsonify({"job_id": job_id, "status": "preview_started"})

    @app.route("/api/jobs/<job_id>")
    def api_job_status(job_id):
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "作业未找到"}), 404
        return jsonify(job)

    @app.route("/api/jobs")
    def api_all_jobs():
        """返回所有作业状态，可选按用户过滤（?phone=xxx）"""
        filter_phone = request.args.get("phone", "").strip()
        items = JOBS.items()
        if filter_phone:
            items = {k: v for k, v in items if v.get("user_phone", "") == filter_phone}.items()
        active = {k: v for k, v in items if v["status"] in ("rendering", "queued", "started")}
        completed = {k: v for k, v in items if v["status"] == "completed"}
        failed = {k: v for k, v in items if v["status"] == "failed"}
        return jsonify({
            "total": len(JOBS),
            "active": len(active),
            "completed": len(completed),
            "failed": len(failed),
            "queue_length": len(BATCH_QUEUE)
        })

    @app.route("/api/download/<job_id>")
    def api_download(job_id):
        job = JOBS.get(job_id)
        if job and job["status"] == "completed":
            output = job.get("output")
            if output and os.path.exists(output):
                return send_file(output, as_attachment=True,
                                 download_name=f"video_{job_id}.mp4",
                                 mimetype="video/mp4")
        # Fallback: 从 user_videos 表查找
        try:
            conn = sqlite3.connect(str(USERS_DB))
            cur = conn.execute("SELECT file_path FROM user_videos WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            conn.close()
            if row and row[0] and os.path.exists(row[0]):
                return send_file(row[0], as_attachment=True,
                                 download_name=f"video_{job_id}.mp4",
                                 mimetype="video/mp4")
        except Exception:
            pass
        # Second fallback: try to find the file in OUTPUT_DIR directly
        output_path = OUTPUT_DIR / f"{job_id}.mp4"
        if output_path.exists():
            return send_file(str(output_path), as_attachment=True,
                             download_name=f"video_{job_id}.mp4",
                             mimetype="video/mp4")
        return jsonify({"error": "视频尚未就绪或文件不存在"}), 404


    @app.route("/api/send-email", methods=["POST"])
    def api_send_email():
        data = request.json or {}
        job_id = data.get("job_id")
        to_email = data.get("to_email", "chuanlbx@qq.com")
        feedback_text = data.get("feedback_text", "").strip()

        # 如果是反馈消息，直接发送
        if feedback_text and not job_id:
            try:
                msg = MIMEText(f"用户反馈：\n\n{feedback_text}", "plain", "utf-8")
                msg["From"] = "chuanlbx@qq.com"
                msg["To"] = to_email
                msg["Subject"] = "用户反馈 - 滇边AI视频工坊"
                smtp = smtplib.SMTP_SSL("smtp.qq.com", 465)
                smtp.login("chuanlbx@qq.com", "uezllxyyasopbijc")
                smtp.send_message(msg)
                smtp.quit()
                logger.info(f"反馈已发送: {feedback_text[:50]}")
                return jsonify({"success": True, "message": "反馈已发送"})
            except Exception as e:
                return jsonify({"error": f"发送失败: {str(e)}"}), 500

        job = JOBS.get(job_id)
        if not job or job["status"] != "completed":
            return jsonify({"error": "视频尚未就緒"}), 404

        output = job.get("output")
        if not output or not os.path.exists(output):
            return jsonify({"error": "文件不存在"}), 404

        try:
            msg = MIMEMultipart()
            msg["From"] = "chuanlbx@qq.com"
            msg["To"] = to_email
            msg["Subject"] = f"视频生成结果 - {job_id}"
            msg.attach(MIMEText("您的视频已生成，请查收附件。", "plain", "utf-8"))

            safe_name = f"video_{job_id}.mp4"
            with open(output, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                msg.attach(part)

            smtp = smtplib.SMTP_SSL("smtp.qq.com", 465)
            smtp.login("chuanlbx@qq.com", "uezllxyyasopbijc")
            smtp.send_message(msg)
            smtp.quit()
            return jsonify({"success": True, "message": f"已发送到 {to_email}"})
        except Exception as e:
            return jsonify({"error": f"邮件发送失败: {str(e)}"}), 500

    @app.route("/api/health")
    def api_health():
        """系统健康检查+状态概览"""
        templates = discover_templates()
        with STATS_LOCK:
            stats = {
                "total_templates": len(templates),
                "active_jobs": len([j for j in JOBS.values() if j["status"] in ("rendering", "queued")]),
                "queue_length": len(BATCH_QUEUE),
                "disk_usage_gb": round(__import__("shutil").disk_usage("/").used / (1024**3), 1),
                "disk_total_gb": round(__import__("shutil").disk_usage("/").total / (1024**3), 1),
                "usage": dict(USAGE_STATS),
                "templates": [{"id": t["id"], "name": t["name"]} for t in templates]
            }
        return jsonify(stats)

    @app.route("/api/stats")
    def api_stats():
        """详细统计：按模板的成功/失败分布"""
        with STATS_LOCK:
            return jsonify(dict(USAGE_STATS))


    @app.route("/api/disk-cleanup", methods=["POST"])
    def api_disk_cleanup():
        """管理员手动触发磁盘清理（需验证token或API Key）"""
        # 简易认证检查：只允许管理员操作
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
        api_key = auth if auth.startswith("hf_") else request.headers.get("X-API-Key", "")
        if not token and not api_key:
            return jsonify({"error": "需要管理员权限"}), 403
        import subprocess
        # 验证身份
        conn = sqlite3.connect(str(USERS_DB))
        cur = None
        if api_key:
            cur = conn.execute("SELECT role FROM users WHERE api_key = ?", (api_key,))
        else:
            cur = conn.execute("SELECT role FROM users WHERE token = ?", (token,))
        row = cur.fetchone()
        conn.close()
        if not row or row[0] != "admin":
            return jsonify({"error": "需要管理员权限"}), 403
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "scripts" / "cleanup_disk.py")],
            capture_output=True, text=True, timeout=120
        )
        return jsonify({
            "success": True,
            "output": result.stdout,
            "error": result.stderr[:500] if result.stderr else ""
        })

    @app.route("/api/generate-variants", methods=["POST"])
    def api_generate_variants():
        """AI文案助手：根据用户输入生成3版文案"""
        data = request.json or {}
        template_id = data.get("template_id", "")
        brand = data.get("brand", "")
        desc = data.get("description", "")
        address = data.get("address", "")
        phone = data.get("phone", "")
        value = data.get("value", "")
        price = data.get("price", "")

        if not template_id or not brand:
            return jsonify({"error": "缺少必要参数"}), 400

        variants = _gen_copy_variants(template_id, brand, desc, address, phone, value, price)

        return jsonify({
            "template_id": template_id,
            "brand": brand,
            "variants": variants
        })


    @app.route("/api/preview-data", methods=["POST"])
    def api_preview_data():
        """Canvas预览：返回模板的关键帧配色和排版数据"""
        data = request.json or {}
        template_id = data.get("template_id", "")

        # 读取模板config获取配色
        for t in discover_templates():
            if t["id"] == template_id:
                cfg = t["config"]
                colors = cfg.get("colors", {})
                bg = cfg.get("background", {})
                return jsonify({
                    "template_name": t["name"],
                    "colors": {
                        "primary": colors.get("primary", "#ffd54f"),
                        "secondary": colors.get("secondary", "#ffffff"),
                        "bg_start": colors.get("bg_start", "#0a2a5e"),
                        "bg_end": colors.get("bg_end", "#060e1e")
                    },
                    "bg_type": bg.get("type", "gradient"),
                    "scenes_count": len(cfg.get("scenes", [])),
                    "audio_config": {
                        "has_voiceover": bool(cfg.get("audio", {}).get("voiceover", {}).get("enabled", True)),
                        "has_bgm": bool(cfg.get("audio", {}).get("bgm", {}).get("enabled", True))
                    }
                })

        return jsonify({"error": "模板未找到"}), 404


    @app.route("/api/preview-canvas", methods=["POST"])
    def api_preview_canvas():
        """预览Canvas数据：返回模板各场景的完整渲染信息，供前端Canvas逐帧绘制预览"""
        data = request.json or {}
        template_id = data.get("template_id", "")
        brand = data.get("brand", "")
        desc = data.get("desc", "")
        phone = data.get("phone", "")
        scenes_text = data.get("scenes_text", None)  # 可选：用户自定义每场景文案

        for t in discover_templates():
            if t["id"] == template_id:
                cfg = t["config"]

                # 1) 获取配色方案
                colors = cfg.get("colors", {})
                color_scheme_id = colors.get("scheme", "warm_dark")
                color_options = colors.get("options", [])

                # 找到当前配色的具体值
                current_colors = {}
                if color_options:
                    for opt in color_options:
                        if opt.get("id") == color_scheme_id:
                            current_colors = {
                                "bg_top": opt.get("bg_top", "#0a1628"),
                                "bg_bottom": opt.get("bg_bottom", "#060e1e"),
                                "white_text": opt.get("white_text", "#ffffff"),
                                "gold_text": opt.get("gold_text", "#ffd54f"),
                                "cyan_text": opt.get("cyan_text", "#00d4ff"),
                                "subtitle_color": opt.get("subtitle_color", "rgba(255,255,255,0.4)")
                            }
                            break
                # fallback: 直接使用 colors 字段
                if not current_colors:
                    current_colors = {
                        "bg_top": colors.get("bg_start", colors.get("bg_top", "#0a1628")),
                        "bg_bottom": colors.get("bg_end", colors.get("bg_bottom", "#060e1e")),
                        "white_text": colors.get("secondary", colors.get("white_text", "#ffffff")),
                        "gold_text": colors.get("gold", colors.get("primary", "#ffd54f")),
                        "cyan_text": colors.get("accent", colors.get("cyan_text", "#00d4ff")),
                        "subtitle_color": colors.get("subtitle_color", "rgba(255,255,255,0.4)")
                    }

                # 2) 解析场景 — 适配多种 scenes 格式
                raw_scenes = cfg.get("scenes", [])
                scenes_data = []

                # 用户自定义文案 (scene_id -> text mapping)
                custom_texts = {}
                if scenes_text:
                    if isinstance(scenes_text, list):
                        if raw_scenes and isinstance(raw_scenes[0], dict) and "id" in raw_scenes[0]:
                            for idx, scene in enumerate(raw_scenes):
                                if idx < len(scenes_text):
                                    custom_texts[scene["id"]] = scenes_text[idx]
                    elif isinstance(scenes_text, dict):
                        custom_texts = scenes_text

                # 判断 scenes 格式类型
                if not raw_scenes:
                    # 空场景 → fallback
                    pass
                elif isinstance(raw_scenes[0], dict) and "text" in raw_scenes[0] and "id" not in raw_scenes[0] and "elements" not in raw_scenes[0]:
                    # 格式2: scenes 是 {"text": "..."} 数组（纯文案列表）
                    for i, sc in enumerate(raw_scenes):
                        text = sc.get("text", "")
                        if "{brand}" in text:
                            text = text.replace("{brand}", brand)
                        if "{phone}" in text:
                            text = text.replace("{phone}", phone or "138xxxxxxxx")
                        if "{address}" in text:
                            text = text.replace("{address}", phone or "地址信息")
                        scenes_data.append({
                            "scene_index": f"s{i+1}",
                            "scene_name": f"场景{i+1}",
                            "duration": 4,
                            "elements": [{
                                "key": "line1",
                                "text": text or "",
                                "font_size": 36,
                                "color": current_colors.get("gold_text", "#ffd54f"),
                                "position": {"x": 0.1, "y": 0.4},
                                "style": "large_gold"
                            }]
                        })
                elif isinstance(raw_scenes[0], str):
                    # 格式3: scenes 是纯字符串数组
                    for i, text in enumerate(raw_scenes):
                        resolved = text
                        if "{brand}" in resolved:
                            resolved = resolved.replace("{brand}", brand)
                        if "{phone}" in resolved:
                            resolved = resolved.replace("{phone}", phone or "138xxxxxxxx")
                        if "{address}" in resolved:
                            resolved = resolved.replace("{address}", phone or "地址信息")
                        scenes_data.append({
                            "scene_index": f"s{i+1}",
                            "scene_name": f"场景{i+1}",
                            "duration": 4,
                            "elements": [{
                                "key": "line1",
                                "text": resolved or "",
                                "font_size": 36,
                                "color": current_colors.get("gold_text", "#ffd54f"),
                                "position": {"x": 0.1, "y": 0.4},
                                "style": "large_gold"
                            }]
                        })
                else:
                    # 格式1（标准格式）: scenes 是对象数组，有 id/elements 等字段
                    for scene in raw_scenes:
                        scene_id = scene.get("id", "")
                        duration = scene.get("duration", 4)
                        elements_raw = scene.get("elements", {})
                        scene_name = scene.get("name", "")

                        elements_info = []

                        # elements 可能是 dict 或 list
                        if isinstance(elements_raw, dict):
                            for key, el in elements_raw.items():
                                text = el.get("text", "")
                                style = el.get("style", "")
                                # 替换占位符
                                brand_placeholders = ["{brand}", "店名", "品牌名", "产品名", "店铺名"]
                                for bp in brand_placeholders:
                                    if text == bp:
                                        text = brand
                                        break
                                if "{brand}" in text:
                                    text = text.replace("{brand}", brand)

                                phone_placeholders = ["{phone}", "电话"]
                                for pp in phone_placeholders:
                                    if text == pp:
                                        text = phone or "138xxxxxxxx"
                                        break
                                if "{phone}" in text:
                                    text = text.replace("{phone}", phone or "138xxxxxxxx")

                                addr_placeholders = ["{address}", "地址"]
                                for ap in addr_placeholders:
                                    if text == ap:
                                        text = phone or "地址信息"
                                        break
                                if "{address}" in text:
                                    text = text.replace("{address}", phone or "地址信息")

                                price_placeholders = ["{price}", "价格"]
                                for pp2 in price_placeholders:
                                    if text == pp2:
                                        text = "¥ 惊喜价"

                                if not text:
                                    text = el.get("text", "")

                                font_size = _get_font_size_for_style(style, el)
                                color = _get_color_for_style(style, current_colors)
                                pos_x = el.get("x", 0.1) if isinstance(el.get("x"), (int, float)) else 0.1
                                pos_y = el.get("y", 0.4) if isinstance(el.get("y"), (int, float)) else 0.4

                                elements_info.append({
                                    "key": key,
                                    "text": text,
                                    "font_size": font_size,
                                    "color": color,
                                    "position": {"x": pos_x, "y": pos_y},
                                    "style": style
                                })
                        elif isinstance(elements_raw, list):
                            for el in elements_raw:
                                text = el.get("text", "")
                                style = el.get("style", "")
                                if "{brand}" in text:
                                    text = text.replace("{brand}", brand)
                                if "{phone}" in text:
                                    text = text.replace("{phone}", phone or "138xxxxxxxx")
                                font_size = _get_font_size_for_style(style, el)
                                color = _get_color_for_style(style, current_colors)
                                elements_info.append({
                                    "key": el.get("key", f"el{len(elements_info)}"),
                                    "text": text or "",
                                    "font_size": font_size,
                                    "color": color,
                                    "position": {"x": el.get("x", 0.1), "y": el.get("y", 0.4)},
                                    "style": style
                                })

                        scenes_data.append({
                            "scene_index": scene_id,
                            "scene_name": scene_name,
                            "duration": duration,
                            "elements": elements_info
                        })

                # 如果场景解析后仍然为空，返回 fallback
                if not scenes_data:
                    return jsonify({
                        "template_name": t["name"],
                        "preview_data": {
                            "fallback": True,
                            "message": "该模板暂不支持Canvas预览，请直接生成视频查看效果",
                            "scenes": [],
                            "colors": current_colors,
                            "animation": {
                                "style": cfg.get("animation", {}).get("style", "fade"),
                                "transition": cfg.get("effects", {}).get("transition_style", "fade")
                            },
                            "bg_type": cfg.get("background", {}).get("type", "gradient"),
                            "output_width": cfg.get("settings", {}).get("output_width", 1080),
                            "output_height": cfg.get("settings", {}).get("output_height", 1920),
                            "audio_info": {
                                "has_voiceover": bool(cfg.get("audio", {}).get("voiceover", {}).get("enabled", True)),
                                "has_bgm": bool(cfg.get("audio", {}).get("bgm", {}).get("enabled", True)),
                                "bgm_options": [o.get("name", "") for o in cfg.get("audio", {}).get("bgm", {}).get("options", []) if o.get("id") != "none"][:3]
                            }
                        }
                    })

                # 3) 动画配置
                animation = cfg.get("animation", {})
                bg_type = cfg.get("background", {}).get("type", "gradient")
                effects = cfg.get("effects", {})

                # 4) 音频信息
                audio_config = cfg.get("audio", {})
                audio_info = {
                    "has_voiceover": bool(audio_config.get("voiceover", {}).get("enabled", True)),
                    "has_bgm": bool(audio_config.get("bgm", {}).get("enabled", True)),
                    "bgm_options": [o.get("name", "") for o in audio_config.get("bgm", {}).get("options", []) if o.get("id") != "none"][:3]
                }

                return jsonify({
                    "template_name": t["name"],
                    "preview_data": {
                        "scenes": scenes_data,
                        "colors": current_colors,
                        "animation": {
                            "style": animation.get("style", "fade"),
                            "transition": effects.get("transition_style", "fade")
                        },
                        "bg_type": bg_type,
                        "output_width": cfg.get("settings", {}).get("output_width", 1080),
                        "output_height": cfg.get("settings", {}).get("output_height", 1920),
                        "audio_info": audio_info
                    }
                })

        return jsonify({"error": "模板未找到"}), 404


    def _get_font_size_for_style(style: str, el: dict) -> int:
        """根据样式名返回Canvas渲染字体大小"""
        size_map = {
            "large_gold": 48,
            "large_white": 44,
            "large_cyan": 36,
            "info": 28,
            "limit": 32,
            "phone": 32,
            "subtitle": 22,
            "price": 48,
        }
        # 优先使用元素上定义的size
        raw_size = el.get("size")
        if isinstance(raw_size, (int, float)):
            return int(raw_size)
        return size_map.get(style, 32)


    def _get_color_for_style(style: str, colors: dict) -> str:
        """根据样式名返回颜色"""
        color_map = {
            "large_gold": colors.get("gold_text", "#ffd54f"),
            "large_white": colors.get("white_text", "#ffffff"),
            "large_cyan": colors.get("cyan_text", "#00d4ff"),
            "info": colors.get("white_text", "#ffffff"),
            "limit": colors.get("gold_text", "#ffd54f"),
            "phone": colors.get("gold_text", "#ffd54f"),
            "subtitle": colors.get("subtitle_color", "rgba(255,255,255,0.4)"),
            "price": colors.get("gold_text", "#ffd54f"),
        }
        return color_map.get(style, colors.get("white_text", "#ffffff"))


    @app.route("/api/one-shot", methods=["POST"])
    def api_one_shot():
        """一句话出片（LLM增强）：用户说一句话，自动匹配模板→生成文案→渲染视频"""
        data = request.json or {}
        user_text = data.get("text", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()

        if not user_text:
            return jsonify({"error": "请说一句话描述你想要的内容"}), 400

        # V5.0: LLM智能匹配（回退关键词）
        if _LLM_AVAILABLE:
            templates_list = discover_templates()
            matched = llm_match_template(user_text, templates_list)
            tid = matched.get("template_id", "food_promo")
            brand = matched.get("brand", user_text[:10])
            desc = matched.get("description", user_text)
        else:
            tid, brand, desc = _smart_match_template(user_text)

        # 获取模板信息
        template = _get_template(tid)
        if not template:
            return jsonify({"error": "无法匹配到合适的模板，尝试说清楚行业/类型"}), 400

        # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
        copy_data = _llm_copy_with_fallback(tid, brand, desc, address, phone)

        # 读取用户个性化设置
        user_bg = data.get("user_bg", "")
        user_color_scheme = data.get("user_color_scheme", "")
        user_brand_watermark = data.get("user_brand_watermark", "")

        params = {
            "text": copy_data["scene_texts"],
            "colors": template["config"].get("colors", {}).get("scheme", "warm_dark"),
            "animation": template["config"].get("animation", {}).get("style", "standard"),
            "bg_type": template["config"].get("background", {}).get("type", "gradient"),
            "quality": "standard",
            "voiceover": {
                "enabled": True,
                "voice": template["config"].get("audio", {}).get("voiceover", {}).get("default_voice", "zh-CN-YunyangNeural"),
                "text": copy_data["voiceover_text"]
            },
            "subtitles": {"enabled": True},
            "bgm": {"enabled": True, "file": "uplifting"},
            "user_bg": user_bg,
            "user_color_scheme": user_color_scheme,
            "user_brand_watermark": user_brand_watermark,
        }

        merged = merge_config_with_user(template["config"], params, is_preview=False)
        job_id = str(uuid.uuid4())[:8]
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        JOBS[job_id] = {"status": "rendering", "progress": 0, "output": None, "error": None, "brand": brand, "template_id": tid, "user_phone": req_user_phone, "_created": time.time()}
        jobs_save(job_id)

        thread = threading.Thread(target=render_video,
                                  args=(Path(template["path"]), merged, job_id))
        thread.start()

        return jsonify({
            "job_id": job_id,
            "status": "started",
            "matched_template": {
                "id": tid,
                "name": template["name"]
            },
            "brand": brand,
            "copy_preview": {
                "scenes": copy_data["scene_texts"],
                "scene_list": [copy_data["scene_texts"].get(f"s{i}", {}).get("line1", "")
                              for i in range(1, 6)
                              if f"s{i}" in copy_data["scene_texts"]],
                "voiceover": copy_data["voiceover_text"]
            }
        })


    @app.route("/api/one-shot-preview", methods=["POST"])
    def api_one_shot_preview():
        """一句话出片预览：只做匹配+文案预览，不渲染"""
        data = request.json or {}
        user_text = data.get("text", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()

        if not user_text:
            return jsonify({"error": "请说一句话描述你想要的内容"}), 400

        # V5.0: LLM智能匹配（回退关键词）
        if _LLM_AVAILABLE:
            templates_list = discover_templates()
            matched = llm_match_template(user_text, templates_list)
            tid = matched.get("template_id", "food_promo")
            brand = matched.get("brand", user_text[:10])
            desc = matched.get("description", user_text)
        else:
            tid, brand, desc = _smart_match_template(user_text)

        # 获取模板信息
        template = _get_template(tid)
        if not template:
            return jsonify({"error": "无法匹配到合适的模板"}), 400

        # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
        copy_data = _llm_copy_with_fallback(tid, brand, desc, address, phone)

        # 兼容scene_texts为list的情况
        st = copy_data["scene_texts"]
        if isinstance(st, list):
            st = {f"s{i+1}": v for i, v in enumerate(st)}

        return jsonify({
            "matched_template": {
                "id": tid,
                "name": template["name"]
            },
            "brand": brand,
            "copy_preview": {
                "scenes": st,
                "scene_list": [st.get(f"s{i}", {}).get("line1", "")
                              for i in range(1, 6)
                              if f"s{i}" in st],
                "voiceover": copy_data["voiceover_text"]
            },
            "scenes_raw": {k: v for k, v in st.items()}
        })


    @app.route("/api/one-shot-apply", methods=["POST"])
    def api_one_shot_apply():
        """一句话出片确认：前端确认文案后开始渲染"""
        data = request.json or {}
        user_text = data.get("text", "").strip()
        phone = data.get("phone", "").strip()
        address = data.get("address", "").strip()
        quality = data.get("quality", "standard")
        scenes_text = data.get("scenes_text", None)  # 用户自定义文案
        voiceover_text = data.get("voiceover_text", None)  # V5.1: 用户自定义配音文本

        if not user_text:
            return jsonify({"error": "请说一句话描述你想要的内容"}), 400

        # V5.0: LLM智能匹配（回退关键词）
        if _LLM_AVAILABLE:
            templates_list = discover_templates()
            matched = llm_match_template(user_text, templates_list)
            tid = matched.get("template_id", "food_promo")
            brand = matched.get("brand", user_text[:10])
            desc = matched.get("description", user_text)
        else:
            tid, brand, desc = _smart_match_template(user_text)

        # 获取模板信息
        template = _get_template(tid)
        if not template:
            return jsonify({"error": "无法匹配到合适的模板"}), 400

        # 如果提供了自定义文案，直接使用
        if scenes_text:
            if isinstance(scenes_text, list):
                text_config = {}
                raw_scenes = template["config"].get("scenes", [])
                for idx, scene in enumerate(raw_scenes):
                    scene_id = scene.get("id", f"s{idx+1}") if isinstance(scene, dict) else f"s{idx+1}"
                    if idx < len(scenes_text):
                        if isinstance(scenes_text[idx], dict):
                            text_config[scene_id] = scenes_text[idx]
                        else:
                            text_config[scene_id] = {"line1": scenes_text[idx]}
                copy_data = {"scene_texts": text_config, "voiceover_text": voiceover_text or ""}
            elif isinstance(scenes_text, dict):
                text_config = {}
                for k, v in scenes_text.items():
                    if isinstance(v, dict):
                        text_config[k] = v
                    else:
                        text_config[k] = {"line1": str(v)}
                copy_data = {"scene_texts": text_config, "voiceover_text": voiceover_text or ""}
            else:
                # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
                copy_data = _llm_copy_with_fallback(tid, brand, desc, address, phone)
        else:
            # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
            copy_data = _llm_copy_with_fallback(tid, brand, desc, address, phone)

        # 读取用户个性化设置
        user_bg = data.get("user_bg", "")
        user_color_scheme = data.get("user_color_scheme", "")
        user_brand_watermark = data.get("user_brand_watermark", "")

        params = {
            "text": copy_data["scene_texts"],
            "colors": template["config"].get("colors", {}).get("scheme", "warm_dark"),
            "animation": template["config"].get("animation", {}).get("style", "standard"),
            "bg_type": template["config"].get("background", {}).get("type", "gradient"),
            "quality": quality,
            "voiceover": {
                "enabled": True,
                "voice": template["config"].get("audio", {}).get("voiceover", {}).get("default_voice", "zh-CN-YunyangNeural"),
                "text": copy_data["voiceover_text"]
            },
            "subtitles": {"enabled": True},
            "bgm": {"enabled": True, "file": "uplifting"},
            "user_bg": user_bg,
            "user_color_scheme": user_color_scheme,
            "user_brand_watermark": user_brand_watermark,
        }

        merged = merge_config_with_user(template["config"], params, is_preview=False)
        job_id = str(uuid.uuid4())[:8]
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        JOBS[job_id] = {"status": "rendering", "progress": 0, "output": None, "error": None, "brand": brand, "template_id": tid, "user_phone": req_user_phone, "_created": time.time()}
        jobs_save(job_id)

        thread = threading.Thread(target=render_video,
                                  args=(Path(template["path"]), merged, job_id))
        thread.start()

        return jsonify({
            "job_id": job_id,
            "status": "started"
        })


    @app.route("/api/bg/stock-search", methods=["POST"])
    def api_stock_search():
        """搜索免费图库图片（预设图片库）"""
        data = request.json or {}
        keyword = data.get("keyword", "").strip()
        category = data.get("category", "").strip()
        count = min(int(data.get("count", 12)), 30)

        # 如果指定了分类，直接使用分类关键词
        search_term = category or keyword
        if not search_term:
            # 返回所有分类的封面图片
            results = []
            for key in STOCK_KEYWORDS:
                images = PRESET_STOCK_IMAGES.get(key, [])
                if images:
                    results.append(images[0])
                if len(results) >= count:
                    break
            return jsonify({"images": results, "total": len(results), "categories": STOCK_KEYWORDS})

        images = search_stock_images(search_term, count)
        return jsonify({"images": images, "total": len(images), "categories": STOCK_KEYWORDS})

    @app.route("/api/preview-copy", methods=["POST"])
    def api_preview_copy():
        """
        文案预览接口：仅生成文案并返回，不启动渲染。
        用户确认文案后再调用 /api/v4/generate 进行渲染。
        """
        data = request.json or {}
        template_id = data.get("template_id", "")
        brand = data.get("brand", "").strip()
        desc = data.get("desc", "").strip()
        address = data.get("address", "").strip()
        phone = data.get("phone", "").strip()
        value = data.get("value", "").strip()
        price = data.get("price", "").strip()
        variant = data.get("variant", "").strip()
        scenes_text = data.get("scenes_text", None)  # 用户自定义文案（可选）

        if not template_id:
            return jsonify({"error": "请提供template_id"}), 400
        if not brand:
            return jsonify({"error": "请填写店名/品牌名"}), 400

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 400

        # 如果提供了自定义文案(scenes_text)，直接使用，否则调用AI生成
        if scenes_text:
            if isinstance(scenes_text, list):
                text_config = {}
                raw_scenes = template["config"].get("scenes", [])
                for idx, scene in enumerate(raw_scenes):
                    scene_id = scene.get("id", f"s{idx+1}") if isinstance(scene, dict) else f"s{idx+1}"
                    if idx < len(scenes_text):
                        if isinstance(scenes_text[idx], dict):
                            text_config[scene_id] = scenes_text[idx]
                        else:
                            text_config[scene_id] = {"line1": scenes_text[idx]}
                copy_data = {"scene_texts": text_config}
            elif isinstance(scenes_text, dict):
                text_config = {}
                for k, v in scenes_text.items():
                    if isinstance(v, dict):
                        text_config[k] = v
                    else:
                        text_config[k] = {"line1": str(v)}
                copy_data = {"scene_texts": text_config}
            else:
                # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
                copy_data = _llm_copy_with_fallback(template_id, brand, desc, address, phone, value=value, price=price)
        else:
            # V5.0: LLM文案优化（优先LLM，失败回退规则引擎）→ _llm_copy_with_fallback
            copy_data = _llm_copy_with_fallback(template_id, brand, desc, address, phone, value=value, price=price)

        # 应用变体微调
        if variant:
            copy_data = _apply_variant_to_copy(copy_data, template_id, variant)

        text_config = copy_data["scene_texts"]
        # 兼容scene_texts为list的情况（某些模板返回列表而非字典）
        if isinstance(text_config, list):
            text_config = {f"s{i+1}": v for i, v in enumerate(text_config)}
        vo_text = copy_data.get("voiceover_text", "")

        # 构建场景列表（用于前端渲染展示）
        scene_list = []
        raw_scenes = template["config"].get("scenes", [])
        for idx, scene in enumerate(raw_scenes):
            scene_id = scene.get("id", f"s{idx+1}") if isinstance(scene, dict) else f"s{idx+1}"
            scene_data = text_config.get(scene_id, {})
            if isinstance(scene_data, dict):
                scene_list.append({
                    "id": scene_id,
                    "line1": scene_data.get("line1", ""),
                    "line2": scene_data.get("line2", ""),
                    "line3": scene_data.get("line3", ""),
                    "line4": scene_data.get("line4", ""),
                    "sub": scene_data.get("sub", ""),
                    "price": scene_data.get("price", ""),
                    "info": scene_data.get("info", ""),
                    "limit": scene_data.get("limit", ""),
                    "address": scene_data.get("address", ""),
                    "phone_str": scene_data.get("phone_str", ""),
                })
            else:
                scene_list.append({"id": scene_id, "line1": str(scene_data)})

        return jsonify({
            "template_id": template_id,
            "brand": brand,
            "copy_preview": {
                "scenes": text_config,
                "scene_list": scene_list,
                "voiceover": vo_text
            }
        })

    @app.route("/api/v4/generate", methods=["POST"])
    def api_v4_generate():
        data = request.json or {}
        template_id = data.get("template_id", "")
        brand = data.get("brand", "").strip()
        desc = data.get("desc", "").strip()
        address = data.get("address", "").strip()
        phone = data.get("phone", "").strip()
        quality = data.get("quality", "standard").strip()
        scenes_text = data.get("scenes_text", None)  # 用户自定义每场景文案
        variant = data.get("variant", None)  # 行业变体（配色+关键词）

        if not template_id:
            return jsonify({"error": "请提供template_id"}), 400
        if not brand:
            return jsonify({"error": "请填写店名/品牌名"}), 400

        template = _get_template(template_id)
        if not template:
            return jsonify({"error": f"模板 {template_id} 不存在"}), 400

        # 如果提供了自定义文案(scenes_text)，直接使用，否则调用AI生成
        if scenes_text:
            # 解析用户自定义文案
            if isinstance(scenes_text, list):
                # list格式：按顺序对应每个场景
                text_config = {}
                raw_scenes = template["config"].get("scenes", [])
                for idx, scene in enumerate(raw_scenes):
                    scene_id = scene.get("id", f"s{idx+1}") if isinstance(scene, dict) else f"s{idx+1}"
                    if idx < len(scenes_text):
                        if isinstance(scenes_text[idx], dict):
                            text_config[scene_id] = scenes_text[idx]
                        else:
                            text_config[scene_id] = {"line1": scenes_text[idx]}
                copy_data = {"scene_texts": text_config}
            elif isinstance(scenes_text, dict):
                # dict格式：{scene_id: text} 或 {scene_id: {line1: text}}
                text_config = {}
                for k, v in scenes_text.items():
                    if isinstance(v, dict):
                        text_config[k] = v
                    else:
                        text_config[k] = {"line1": str(v)}
                copy_data = {"scene_texts": text_config}
            else:
                copy_data = _llm_copy_with_fallback(template_id, brand, desc, address, phone)
        else:
            copy_data = _llm_copy_with_fallback(template_id, brand, desc, address, phone)

        # 构建渲染参数
        text_config = copy_data["scene_texts"]
        vo_text = copy_data.get("voiceover_text", "")

        # 读取用户个性化设置（前端通过参数传入）
        user_bg = data.get("user_bg", "")
        user_color_scheme = data.get("user_color_scheme", "")
        user_brand_watermark = data.get("user_brand_watermark", "")
        user_bg_scenes = data.get("user_bg_scenes", [])

        params = {
            "text": text_config,
            "animation": template["config"].get("animation", {}).get("style", "standard"),
            "bg_type": template["config"].get("background", {}).get("type", "gradient"),
            "quality": quality,
            "voiceover": {
                "enabled": True,
                "voice": template["config"].get("audio", {}).get("voiceover", {}).get("default_voice", "zh-CN-YunyangNeural"),
                "text": vo_text
            },
            "subtitles": {"enabled": True},
            "bgm": {"enabled": True, "file": "uplifting"},
            "user_bg": user_bg,
            "user_color_scheme": user_color_scheme,
            "user_brand_watermark": user_brand_watermark,
            "user_bg_scenes": user_bg_scenes,
        }

        # 应用行业变体（配色+关键词覆盖）
        if variant and isinstance(variant, dict):
            colors = variant.get("colors", {})
            if colors:
                params["colors"] = {
                    "primary": colors.get("primary", "#ffd54f"),
                    "bg_start": colors.get("bg_start", "#0a2a5e"),
                    "bg_end": colors.get("bg_end", "#060e1e"),
                }
            keywords = variant.get("keywords", [])
            if keywords:
                params["keywords"] = keywords
            voiceover_hint = variant.get("voiceover_hint", "")
            if voiceover_hint and not vo_text:
                params["voiceover"]["text"] = voiceover_hint

        merged = merge_config_with_user(template["config"], params, is_preview=False)
        job_id = str(uuid.uuid4())[:8]
        # 获取当前用户（如果已登录）
        req_user_phone = ""
        if hasattr(request, 'user') and request.user:
            req_user_phone = request.user.get("phone", "")
        JOBS[job_id] = {"status": "queued", "progress": 0, "output": None, "error": None, "brand": brand, "template_id": template_id, "user_phone": req_user_phone, "_created": time.time()}
        jobs_save(job_id)

        # 加入渲染队列
        queue_render(job_id, Path(template["path"]), merged)

        return jsonify({"job_id": job_id, "status": "queued"})

    @app.route("/api/generate-xiaohongshu-copy", methods=["POST"])
    def api_generate_xiaohongshu_copy():
        """根据job_id生成小红书风格的分享文案"""
        data = request.json or {}
        job_id = data.get("job_id", "").strip()

        if not job_id or job_id not in JOBS:
            # 无job信息，返回通用文案
            return jsonify({"copy": "\u2728 \u8fd9\u4e2a\u89c6\u9891\u505a\u5f97\u4e5f\u592a\u7edd\u4e86\u5427\uff01\uff01\n\n\u7528AI\u505a\u7684\u5ba3\u4f20\u89c6\u9891\uff0c\u592a\u6709\u611f\u89c9\u4e86\ud83d\udd25\n\u4ece\u6587\u6848\u5230\u753b\u9762\u5230\u914d\u97f3\uff0c\u5168\u7a0bAI\u641e\u5b9a\n\u6548\u679c\u5b8c\u5168\u4e0d\u8f93\u7ed9\u82b1\u94b1\u627e\u56e2\u961f\u505a\u7684\n\n\u518d\u4e5f\u4e0d\u7528\u6101\u505a\u89c6\u9891\u4e86\uff0c\u5c0f\u767d\u4e5f\u80fd\u51fa\u5927\u7247\ud83c\udfa5\n\u76f4\u63a5\u4e0a\u94fe\u63a5\uff0c\u4f60\u4e5f\u6765\u8bd5\u8bd5\ud83d\udc47\n\n#AI\u89c6\u9891 #\u4eba\u5de5\u667a\u80fd #\u6548\u7387\u5de5\u5177 #\u6587\u5c71 #\u6ec7\u8fb9AI"}), 200

        job = JOBS[job_id]
        brand = job.get("brand", "")
        template_id = job.get("template_id", "")

        # 生成小红书风格文案
        lines = []
        lines.append("\u2728 \u8fd9\u4e2a\u89c6\u9891\u505a\u5f97\u4e5f\u592a\u7edd\u4e86\u5427\uff01\uff01")
        lines.append("")
        if brand:
            lines.append(f"\u7528AI\u505a\u7684 {brand} \u5ba3\u4f20\u89c6\u9891\uff0c\u592a\u6709\u611f\u89c9\u4e86\ud83d\udd25")
        else:
            lines.append("\u7528AI\u505a\u7684\u5ba3\u4f20\u89c6\u9891\uff0c\u592a\u6709\u611f\u89c9\u4e86\ud83d\udd25")
        lines.append("\u4ece\u6587\u6848\u5230\u753b\u9762\u5230\u914d\u97f3\uff0c\u5168\u7a0bAI\u641e\u5b9a")
        lines.append("\u6548\u679c\u5b8c\u5168\u4e0d\u8f93\u7ed9\u82b1\u94b1\u627e\u56e2\u961f\u505a\u7684")
        lines.append("")
        lines.append("\u518d\u4e5f\u4e0d\u7528\u6101\u505a\u89c6\u9891\u4e86\uff0c\u5c0f\u767d\u4e5f\u80fd\u51fa\u5927\u7247\ud83c\udfa5")
        lines.append("\u76f4\u63a5\u4e0a\u94fe\u63a5\uff0c\u4f60\u4e5f\u6765\u8bd5\u8bd5\ud83d\udc47")
        lines.append("")
        lines.append("#AI\u89c6\u9891 #\u4eba\u5de5\u667a\u80fd #\u6548\u7387\u5de5\u5177 #\u6587\u5c71 #\u6ec7\u8fb9AI")

        return jsonify({"copy": "\n".join(lines)})

