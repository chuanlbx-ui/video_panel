#!/usr/bin/env python3
"""
api_video_analysis.py — 视频分析四步工作流
包含4个API路由和异步分析工作流管理

功能:
  1. POST /api/analyze-video          — 启动视频分析任务
  2. GET  /api/analyze-status/<job_id> — 查询分析任务状态
  3. POST /api/analyze-to-template    — 分析结果 → template_config
  4. POST /api/analyze-generate       — 使用分析生成的模板渲染视频

使用 init_routes(app) 模式注册路由
"""
import json, os, sys, uuid, threading, time, traceback, logging
from pathlib import Path
from flask import request, jsonify

logger = logging.getLogger(__name__)

# ===================== 导入分析模块 =====================
try:
    from video_analyzer.video_downloader import download_video
    from video_analyzer.scene_detector import detect_scenes
    from video_analyzer.speech_analyzer import analyze_speech
    from video_analyzer.visual_analyzer import analyze_visuals
    from video_analyzer.structure_analyzer import analyze_structure
    _ANALYZER_READY = True
    logger.info("[分析模块] 视频分析模块已加载")
except ImportError as e:
    _ANALYZER_READY = False
    logger.warning(f"[分析模块] 部分分析模块导入失败: {e}")
except Exception as e:
    _ANALYZER_READY = False
    logger.warning(f"[分析模块] 分析模块加载异常: {e}")

# ===================== template_generator 可选导入 =====================
try:
    from template_generator import analysis_to_template
    _TEMPLATE_GEN_READY = True
    logger.info("[模板生成] template_generator 已就绪")
except ImportError:
    _TEMPLATE_GEN_READY = False
    logger.warning("[模板生成] template_generator 未找到，使用内置简单转换")
except Exception as e:
    _TEMPLATE_GEN_READY = False
    logger.warning(f"[模板生成] template_generator 加载异常: {e}")

# ===================== 渲染管线导入 =====================
try:
    from hyperframes_app import BASE_DIR, OUTPUT_DIR, JOBS, JOBS_LOCK, jobs_save
    from api_video import render_video, merge_config_with_user, _get_template
    _RENDER_READY = True
except ImportError as e:
    _RENDER_READY = False
    logger.warning(f"[渲染] 渲染管线导入失败: {e}")
    # 回退定义
    BASE_DIR = Path(__file__).parent
    OUTPUT_DIR = BASE_DIR / "output"
    OUTPUT_DIR.mkdir(exist_ok=True)
    JOBS = {}
    JOBS_LOCK = threading.Lock()
    def jobs_save(job_id): pass
    def render_video(*args, **kwargs):
        raise RuntimeError("渲染管线不可用")
    def merge_config_with_user(*args, **kwargs):
        raise RuntimeError("merge_config_with_user 不可用")
    def _get_template(*args, **kwargs):
        return None

# ===================== 分析任务管理 =====================

ANALYSIS_JOBS = {}       # {job_id: {status, progress, result, error, created_at}}
ANALYSIS_JOBS_LOCK = threading.Lock()
WORK_DIR = Path("/home/agentuser/hyperframes_projects/analysis_workdir")
WORK_DIR.mkdir(parents=True, exist_ok=True)

# 持久化文件
ANALYSIS_JOBS_FILE = WORK_DIR / "analysis_jobs.json"


def _analysis_jobs_save():
    """持久化 ANALYSIS_JOBS 到文件"""
    try:
        with ANALYSIS_JOBS_LOCK:
            data = {}
            for jid, j in ANALYSIS_JOBS.items():
                # 只保留序列化的字段
                data[jid] = {
                    "status": j.get("status"),
                    "progress": j.get("progress", 0),
                    "result": j.get("result"),
                    "error": j.get("error"),
                    "created_at": j.get("created_at"),
                    "url": j.get("url", ""),
                }
            with open(ANALYSIS_JOBS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"[持久化] 保存分析作业失败: {e}")


def _analysis_jobs_load():
    """从文件加载 ANALYSIS_JOBS"""
    global ANALYSIS_JOBS
    try:
        if ANALYSIS_JOBS_FILE.exists():
            with open(ANALYSIS_JOBS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                with ANALYSIS_JOBS_LOCK:
                    ANALYSIS_JOBS.update(data)
            logger.info(f"[持久化] 已加载 {len(data)} 个分析作业")
    except Exception as e:
        logger.warning(f"[持久化] 加载分析作业失败: {e}")


def _update_analysis_progress(job_id: str, progress: int, status: str = None):
    """更新分析任务进度并持久化"""
    try:
        with ANALYSIS_JOBS_LOCK:
            if job_id in ANALYSIS_JOBS:
                ANALYSIS_JOBS[job_id]["progress"] = progress
                if status:
                    ANALYSIS_JOBS[job_id]["status"] = status
        logger.info(f"[分析进度] {job_id}: {progress}% ({status or '进行中'})")
        _analysis_jobs_save()
    except Exception:
        pass


# ===================== 分析工作线程 =====================

def _analysis_worker(job_id: str, url: str):
    """依次调用5个分析模块，更新JOB进度"""
    logger.info(f"[分析线程] 启动分析任务 {job_id}, url={url[:80]}...")
    try:
        work_dir = WORK_DIR / job_id
        work_dir.mkdir(exist_ok=True)

        # 1. 下载视频 (progress 0→20)
        _update_analysis_progress(job_id, 5, "analyzing")
        logger.info(f"[分析] {job_id}: 开始下载视频...")
        dl = download_video(url, str(work_dir))
        if not dl.get("success"):
            raise Exception(dl.get("error", "下载失败"))
        logger.info(f"[分析] {job_id}: 视频下载完成, 时长={dl.get('duration', '?')}s")

        # 2. 场景检测 (progress 20→35)
        _update_analysis_progress(job_id, 20)
        logger.info(f"[分析] {job_id}: 开始场景检测...")
        scenes = detect_scenes(dl["video_path"])
        logger.info(f"[分析] {job_id}: 场景检测完成, 共{len(scenes) if isinstance(scenes, list) else '?'}个场景")

        # 3. 语音分析 (progress 35→55)
        _update_analysis_progress(job_id, 35)
        logger.info(f"[分析] {job_id}: 开始语音分析...")
        speech = analyze_speech(dl["audio_path"])
        logger.info(f"[分析] {job_id}: 语音分析完成")

        # 4. 视觉分析 (progress 55→75)
        _update_analysis_progress(job_id, 55)
        logger.info(f"[分析] {job_id}: 开始视觉分析...")
        visuals = analyze_visuals(dl["video_path"], scenes)
        logger.info(f"[分析] {job_id}: 视觉分析完成")

        # 5. 结构分析 (progress 75→90)
        _update_analysis_progress(job_id, 75)
        logger.info(f"[分析] {job_id}: 开始结构分析...")
        structure = analyze_structure(
            speech.get("segments", []),
            scenes,
            visuals
        )
        logger.info(f"[分析] {job_id}: 结构分析完成")

        # 合并结果
        result = {**dl, **speech, **visuals, **structure}
        result["_raw_scenes"] = scenes
        # 清理不需要的字段
        for k in ["video_path", "audio_path", "success"]:
            result.pop(k, None)

        with ANALYSIS_JOBS_LOCK:
            ANALYSIS_JOBS[job_id]["result"] = result
            ANALYSIS_JOBS[job_id]["status"] = "completed"
            ANALYSIS_JOBS[job_id]["progress"] = 100
        _analysis_jobs_save()
        logger.info(f"[分析] {job_id}: 分析完成 ✓")

    except Exception as e:
        error_msg = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"[分析] {job_id}: 分析失败: {error_msg}")
        logger.error(traceback_str)
        with ANALYSIS_JOBS_LOCK:
            ANALYSIS_JOBS[job_id]["status"] = "failed"
            ANALYSIS_JOBS[job_id]["error"] = error_msg
            ANALYSIS_JOBS[job_id]["traceback"] = traceback_str
        _analysis_jobs_save()


# ===================== 内置 template 转换（回退函数） =====================

def _simple_analysis_to_template(analysis_result: dict, template_name: str = "ai_generated") -> dict:
    """
    简单版本的分析结果→template_config转换
    当 template_generator 不可用时作为回退
    """
    scenes = analysis_result.get("_raw_scenes", [])
    structure = analysis_result.get("scenes", analysis_result.get("structured_scenes", []))

    template_scenes = []
    for i, scene_info in enumerate(structure if structure else scenes[:5]):
        scene_id = f"scene_{i:02d}"
        # 尝试从分析结果提取文案
        text_content = ""
        if isinstance(scene_info, dict):
            text_content = scene_info.get("title", scene_info.get("text", scene_info.get("description", f"场景 {i+1}")))
        else:
            text_content = f"场景 {i+1}"

        scene = {
            "id": scene_id,
            "duration": scene_info.get("duration", 4.0) if isinstance(scene_info, dict) else 4.0,
            "elements": {
                "title": {"text": text_content, "font_size": 48},
                "subtitle": {"text": "", "font_size": 32}
            }
        }
        template_scenes.append(scene)

    template_config = {
        "template_name": template_name,
        "width": analysis_result.get("width", 1080),
        "height": analysis_result.get("height", 1920),
        "duration": analysis_result.get("duration", 30.0),
        "colors": {
            "scheme": "warm_dark",
            "primary": "#E8491D",
            "secondary": "#FFD700",
            "bg_start": "#1a1a2e",
            "bg_end": "#16213e"
        },
        "animation": {
            "style": "standard",
            "transition": "fade"
        },
        "background": {
            "type": "gradient",
            "color_start": "#1a1a2e",
            "color_end": "#16213e"
        },
        "audio": {
            "voiceover": {"enabled": True, "voice": "zh-CN-YunyangNeural"},
            "bgm": {"enabled": True, "file": "uplifting"}
        },
        "subtitles": {"enabled": True},
        "scenes": template_scenes,
        "settings": {
            "fps": 30,
            "output_width": 1080,
            "output_height": 1920,
            "quality": "standard",
            "video_bitrate": "10M",
            "pixel_format": "yuv420p"
        },
        "effects": {
            "transition_style": "fade",
            "particle_density": "medium",
            "glow_enabled": False
        },
        "_source": "ai_analysis",
        "_analysis_job_id": analysis_result.get("_analysis_job_id", "")
    }

    return template_config


# ===================== API 端点 1: 启动分析 =====================

def api_analyze_video():
    """启动视频分析任务"""
    if not _ANALYZER_READY:
        return jsonify({"error": "分析模块未就绪，请检查模块导入"}), 503

    data = request.json or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "请提供视频URL (url)"}), 400

    # 生成job_id
    job_id = "analysis_" + str(uuid.uuid4())[:8]

    # 初始化任务记录
    with ANALYSIS_JOBS_LOCK:
        ANALYSIS_JOBS[job_id] = {
            "status": "analyzing",
            "progress": 0,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "url": url,
        }
    _analysis_jobs_save()

    # 启动后台分析线程
    thread = threading.Thread(target=_analysis_worker, args=(job_id, url), daemon=True)
    thread.start()

    logger.info(f"[API] 启动视频分析: job_id={job_id}, url={url[:80]}...")
    return jsonify({
        "job_id": job_id,
        "status": "analyzing",
        "progress": 0,
        "message": "视频分析已启动"
    })


# ===================== API 端点 2: 查询状态 =====================

def api_analyze_status(job_id):
    """查询分析任务状态（从文件加载，兼容多worker）"""
    _analysis_jobs_load()
    
    with ANALYSIS_JOBS_LOCK:
        job = ANALYSIS_JOBS.get(job_id)

    if not job:
        return jsonify({"error": f"分析任务 {job_id} 不存在"}), 404

    resp = {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "created_at": job.get("created_at"),
    }

    if job.get("status") == "completed":
        resp["result"] = job.get("result")
    elif job.get("status") == "failed":
        resp["error"] = job.get("error")

    return jsonify(resp)


# ===================== API 端点 3: 分析结果→模板 =====================

def api_analyze_to_template():
    """分析结果 → template_config"""
    data = request.json or {}
    analysis_job_id = data.get("analysis_job_id", "").strip()
    template_name = data.get("template_name", "ai_analyzed_video").strip()

    if not analysis_job_id:
        return jsonify({"error": "请提供 analysis_job_id"}), 400

    # 从文件加载分析结果（兼容多worker）
    _analysis_jobs_load()
    
    # 获取分析结果
    with ANALYSIS_JOBS_LOCK:
        job = ANALYSIS_JOBS.get(analysis_job_id)

    if not job:
        return jsonify({"error": f"分析任务 {analysis_job_id} 不存在"}), 404

    if job.get("status") != "completed":
        return jsonify({"error": f"分析任务尚未完成，当前状态: {job.get('status')}"}), 400

    result = job.get("result")
    if not result:
        return jsonify({"error": "分析结果为空"}), 500

    # 生成模板ID和目录
    template_id = "ai_analyzed_" + str(uuid.uuid4())[:8]
    template_dir = Path(f"/home/agentuser/hyperframes_projects/{template_id}")
    template_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 尝试使用 template_generator 生成模板配置
        if _TEMPLATE_GEN_READY:
            logger.info(f"[模板生成] 使用 template_generator 生成模板配置...")
            template_config = analysis_to_template(result, template_name)
        else:
            logger.info(f"[模板生成] 使用内置简单转换...")
            template_config = _simple_analysis_to_template(result, template_name)

        # 确保模板配置包含源信息
        template_config["_analysis_job_id"] = analysis_job_id
        template_config["template_name"] = template_name

        # 保存模板配置
        config_path = template_dir / "template_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(template_config, f, ensure_ascii=False, indent=2)

        # 复制默认 build_from_config.py（如果存在）
        default_build = Path(__file__).parent / "build_engine.py"
        target_build = template_dir / "build_from_config.py"
        if not target_build.exists():
            # 尝试从现有模板复制
            sample_template = Path(__file__).parent / "food_promo"
            sample_build = sample_template / "build_from_config.py"
            if sample_build.exists():
                import shutil
                shutil.copy(str(sample_build), str(target_build))
                logger.info(f"[模板生成] 已复制 build_from_config.py")
            else:
                logger.warning(f"[模板生成] 未找到 build_from_config.py 模板")

        logger.info(f"[模板生成] 模板已保存: {config_path}")
        return jsonify({
            "template_id": template_id,
            "template_config": template_config,
            "template_dir": str(template_dir),
            "status": "ready",
            "message": "模板生成成功"
        })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[模板生成] 失败: {error_msg}")
        traceback.print_exc()
        return jsonify({"error": f"模板生成失败: {error_msg}"}), 500


# ===================== API 端点 4: 使用分析模板渲染 =====================

def api_analyze_generate():
    """使用分析生成的模板渲染视频"""
    if not _RENDER_READY:
        return jsonify({"error": "渲染管线不可用"}), 503

    data = request.json or {}
    template_id = data.get("template_id", "").strip()
    user_params = data.get("user_params", {})

    if not template_id:
        return jsonify({"error": "请提供 template_id"}), 400

    # 读取模板配置
    template_dir = Path(f"/home/agentuser/hyperframes_projects/{template_id}")
    config_path = template_dir / "template_config.json"

    if not config_path.exists():
        return jsonify({"error": f"模板 {template_id} 不存在或配置丢失"}), 404

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            template_config = json.load(f)
    except Exception as e:
        return jsonify({"error": f"读取模板配置失败: {e}"}), 500

    # 合并用户参数
    merged = merge_config_with_user(template_config, user_params, is_preview=False)

    # 创建渲染任务
    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "status": "rendering",
        "progress": 0,
        "output": None,
        "error": None,
        "template_id": template_id,
        "_created": time.time(),
        "source": "ai_analysis"
    }
    jobs_save(job_id)

    # 启动渲染线程
    thread = threading.Thread(
        target=render_video,
        args=(template_dir, merged, job_id),
        daemon=True
    )
    thread.start()

    logger.info(f"[API] 启动分析模板渲染: job_id={job_id}, template_id={template_id}")
    return jsonify({
        "job_id": job_id,
        "status": "rendering",
        "progress": 0,
        "message": "视频渲染已启动"
    })


# ===================== 路由注册 =====================

def init_routes(app):
    """注册所有分析相关的路由到Flask app"""
    # 启动时加载持久化数据
    _analysis_jobs_load()

    @app.route("/api/analyze-video", methods=["POST"])
    def _api_analyze_video():
        return api_analyze_video()

    @app.route("/api/analyze-status/<job_id>", methods=["GET"])
    def _api_analyze_status(job_id):
        return api_analyze_status(job_id)

    @app.route("/api/analyze-to-template", methods=["POST"])
    def _api_analyze_to_template():
        return api_analyze_to_template()

    @app.route("/api/analyze-generate", methods=["POST"])
    def _api_analyze_generate():
        return api_analyze_generate()

    logger.info("[路由] 已注册 4 个分析相关路由:")
    logger.info("  POST /api/analyze-video")
    logger.info("  GET  /api/analyze-status/<job_id>")
    logger.info("  POST /api/analyze-to-template")
    logger.info("  POST /api/analyze-generate")


# ===================== 独立测试 =====================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=" * 60)
    print("api_video_analysis.py — 视频分析工作流模块")
    print("=" * 60)
    print(f"  分析模块就绪: {_ANALYZER_READY}")
    print(f"  模板生成就绪: {_TEMPLATE_GEN_READY}")
    print(f"  渲染管线就绪: {_RENDER_READY}")
    print(f"  工作目录: {WORK_DIR}")
    print("=" * 60)
    print("\n通过 init_routes(app) 注册到 Flask 应用")
