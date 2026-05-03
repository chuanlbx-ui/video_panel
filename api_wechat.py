#!/usr/bin/env python3
"""
微信推送模块 — 视频生成完成后推送消息到微信群（含邀请裂变链接）
使用 init_routes(app) 模式注册路由
"""
import json, os, logging
from pathlib import Path
from flask import request, jsonify

logger = logging.getLogger(__name__)

# 从主模块引入共享变量
from hyperframes_app import BASE_DIR, JOBS
from api_templates import discover_templates

# ===================== 模块级数据 =====================

PUSH_QUEUE_DIR = Path(os.path.expanduser("~/.hermes/services/wechat_bridge/push_queue"))
PUSH_QUEUE_DIR.mkdir(exist_ok=True)

# 分享裂变基础链接
INVITE_LINK_BASE = "ws.aiedu.yn.cn"


# ===================== 路由注册 =====================

def init_routes(app):
    """注册所有微信推送相关路由"""

    @app.route("/api/push-wechat", methods=["POST"])
    def api_push_wechat():
        """视频生成完成后，推送消息到微信群（含邀请裂变链接）"""
        data = request.json or {}
        job_id = data.get("job_id", "").strip()
        group_name = data.get("group_name", "").strip()
        invite_code = data.get("invite_code", "").strip()
        user_name = data.get("user_name", "").strip()

        if not job_id:
            return jsonify({"error": "缺少 job_id"}), 400

        job = JOBS.get(job_id)
        if not job or job["status"] != "completed":
            return jsonify({"error": "视频尚未就绪"}), 400

        output = job.get("output")
        if not output or not os.path.exists(output):
            return jsonify({"error": "文件不存在"}), 404

        # 获取视频下载链接
        video_url = f"{request.host_url}video-panel/api/download/{job_id}"
        file_size = os.path.getsize(output) / (1024 * 1024)
        job_title = os.path.basename(output)

        # 构造邀请链接文案
        invite_link = f"{INVITE_LINK_BASE}?ref={invite_code}" if invite_code else None
        if user_name and invite_link:
            share_text = f"🎬 {user_name}用滇边AI做了个视频！你也来试试 → {invite_link}"
        else:
            share_text = (
                f"🎬 你的AI视频已生成！\n"
                f"点击链接下载查看：{video_url}\n"
                f"文件大小：{file_size:.1f}MB\n"
                f"下载后可直接在微信群分享～"
            )

        # 写入推送队列
        if not PUSH_QUEUE_DIR.exists():
            PUSH_QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        push_data = {
            "group_name": group_name or "文山州互联网协会",
            "content": share_text,
            "type": "video_link",
            "job_id": job_id,
            "video_url": video_url,
            "timestamp": __import__("time").time(),
        }

        push_file = PUSH_QUEUE_DIR / f"push_{__import__('time').time()}.json"
        with open(push_file, "w", encoding="utf-8") as f:
            json.dump(push_data, f, ensure_ascii=False)

        logger.info(f"[微信推送] 视频 {job_id} 已加入推送队列 -> {group_name}")
        return jsonify({"success": True, "message": f"已加入推送队列，等待客户端发送到群【{group_name or '默认群'}】"})
