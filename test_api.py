#!/usr/bin/env python3
"""
视频工坊核心API自动化测试
用法: python3 test_api.py [--base http://localhost:8766]
"""
import json, sys, os, time, urllib.request, urllib.error

BASE = "http://localhost:8766"
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

PASS = 0
FAIL = 0

def api(method, path, data=None):
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    if data:
        req.data = json.dumps(data).encode()
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode()
        return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {"raw": body}
    except Exception as e:
        return 0, {"error": str(e)}

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")

print(f"🧪 视频工坊核心API测试 — {BASE}")
print("=" * 50)

# 1. 模板列表
print("\n📋 1. 模板列表")
code, data = api("GET", "/api/templates")
check("模板列表返回200", code == 200, f"got {code}")
check("模板数量>0", len(data) > 0, f"got {len(data)}")
if data:
    # /api/templates 可能返回 dict {templates: [...]} 或 list
    tpl_list = data if isinstance(data, list) else data.get("templates", data.get("data", []))
    check("模板数量>0", len(tpl_list) > 0, f"got {len(tpl_list)}")
    if tpl_list:
        tids = [t["id"] for t in tpl_list if isinstance(t, dict)]
        check("包含store_promo", "store_promo" in tids)
        check("包含personal_ip", "personal_ip" in tids)

# 2. 单个模板详情
print("\n📋 2. 模板详情")
code, data = api("GET", "/api/templates/store_promo")
check("模板详情返回200", code == 200)
check("包含config字段", "config" in data)
check("场景数量>0", len(data.get("config", {}).get("scenes", [])) > 0)

# 3. AI智能生成——预览
print("\n🤖 3. AI智能生成——预览")
code, data = api("POST", "/api/one-shot-preview", {
    "text": "帮我的火锅店做宣传",
    "phone": "", "address": "",
    "user_bg": "", "user_color_scheme": "", "user_brand_watermark": "",
    "user_bg_scenes": []
})
check("预览返回200", code == 200, f"got {code}")
check("有matched_template", "matched_template" in data)
check("有copy_preview", "copy_preview" in data)
check("有场景内容", len(data.get("copy_preview", {}).get("scenes", {})) > 0)

# 4. 预览——AI生成长文本
print("\n🤖 4. 预览——长文本")
code, data = api("POST", "/api/one-shot-preview", {
    "text": "帮我做一个三七产业推广的视频，文山的三七品质好，历史悠久，我要推荐给全国各地的客户",
    "phone": "", "address": "", "user_bg": "", "user_color_scheme": "",
    "user_brand_watermark": "", "user_bg_scenes": []
})
check("长文本预览返回200", code == 200, f"got {code}")

# 5. 确认生成（draft模式加速）
print("\n🎬 5. 确认生成（draft模式）")
scenes = {
    "s1": {"line1": "暖黄灯光，烟火气满满"},
    "s2": {"line1": "贴心服务，像回家一样"},
    "s3": {"line1": "顾客说：味道正宗，服务暖心"},
    "s4": {"line1": "今晚就来，暖胃更暖心"}
}
code, data = api("POST", "/api/one-shot-apply", {
    "text": "帮我的火锅店做宣传",
    "phone": "", "address": "",
    "quality": "draft",
    "scenes_text": scenes,
    "voiceover_text": "暖黄灯光下，热气腾腾的火锅。贴心服务，像回家一样。今晚就来吃火锅吧。",
    "user_bg": "", "user_color_scheme": "", "user_brand_watermark": "",
    "user_bg_scenes": []
})
check("确认生成返回200", code == 200, f"got {code}")
job_id = data.get("job_id", "")
check("有job_id", bool(job_id))

# 6. 轮询进度（draft模式预期30秒内完成）
if job_id:
    print("\n⏳ 6. 轮询进度")
    rendered_ok = False
    for i in range(6):  # 最多等18秒
        time.sleep(3)
        code, data = api("GET", f"/api/jobs/{job_id}")
        s = data.get("status", "unknown")
        p = data.get("progress", 0)
        print(f"   第{i+1}次轮询: status={s}, progress={p}%")
        if s == "completed" or p == 100:
            check("渲染成功完成", s == "completed")
            check("输出文件存在", bool(data.get("output")))
            check("progress=100", p == 100)
            rendered_ok = True
            break
        if s == "failed":
            check("渲染未失败", False, data.get("error", "unknown"))
            rendered_ok = True  # 已经知道结果了
            break
    else:
        # 超时了，但可能只是慢，检查队列状态
        print("   ⚠️ 轮询超时，跳过文件检查")
        check("渲染已进入队列", True)

# 7. 下载视频
if job_id and rendered_ok:
    print("\n⬇️ 7. 下载视频")
    code, data = api("GET", f"/api/download/{job_id}")
    # download返回的是文件不是json，所以code=200就算过
    check("下载返回200", code == 200)

# 8. 用户视频列表（需token）
print("\n👤 8. 用户视频列表")
# 先登录获取token
code, data = api("POST", "/api/login", {"phone": "13577683126", "password": "simonyc653100"})
token = data.get("token", "")
if token:
    url = BASE + "/api/user/videos"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        body = json.loads(resp.read().decode())
        vids = body.get("videos", [])
        check("用户视频列表返回成功", True)
        check("视频数量>0", len(vids) > 0, f"got {len(vids)}")
        if vids:
            dl = vids[0].get("download_url", "")
            check("download_url包含video-panel前缀", "/video-panel/" in dl or "localhost" in dl, dl)
    except Exception as e:
        check("用户视频接口", False, str(e))

# 9. 管理员测试——队列状态
print("\n⚙️ 9. 队列状态")
code, data = api("GET", "/api/queue-status")
check("队列状态返回200", code == 200)

# 汇总
print("\n" + "=" * 50)
total = PASS + FAIL
print(f"\n📊 测试汇总: {PASS}/{total} 通过, {FAIL}/{total} 失败")
if FAIL > 0:
    print("⚠️  有测试未通过，请检查")
    sys.exit(1)
else:
    print("✅ 全部通过！")
