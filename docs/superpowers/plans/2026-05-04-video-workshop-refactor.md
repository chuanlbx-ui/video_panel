# 视频工坊后端重构 + 前端优化 实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (via delegate_task) or executing-plans (via todo) to implement this plan task-by-task. 使用 subagent-driven-development 流程：每任务一个 subagent，实现后跑测试，然后 git commit。

**目标:** 将5000行单体 `hyperframes_app.py` 拆分为6个独立功能模块 + 将2467行前端单页面 `index_v4_phone.html` 模块化优化，提升可维护性和开发效率。

**架构:** 后端按业务领域拆分（Flask Blueprint模式），每个模块独自加载路由，主入口仅负责注册和初始化。前端按屏幕状态拆分 JS 逻辑，全局状态收敛到单一 AppState 对象。

**Tech Stack:** Flask (Python) + Vanilla JS + SQLite + hyperframes渲染引擎

---

## 第一阶段：后端拆分（6个子任务）

### 文件结构规划

```
hyperframes_app.py → 入口(路由注册+初始化+中间件, ~600行)
                    ├── api_templates.py (模板管理: CRUD + 克隆 + 配置, ~500行)
                    ├── api_video.py     (渲染/生成/下载/C任务, ~800行)
                    ├── api_user.py      (用户/登录/权限/APIKey/用量, ~500行)
                    ├── api_admin.py     (管理后台: 用户/模板/用量, ~800行)
                    ├── api_bg.py        (背景素材管理, ~400行)
                    └── api_wechat.py    (微信推送/变体/裂变, ~400行)
```

每个模块暴露一个 `register_routes(app)` 函数，入口 `hyperframes_app.py` 调用注册。

**注意事项（重要！）**
1. 拆分过程中**不修改任何业务逻辑**，只做代码搬迁和 import 调整
2. 共享数据（`JOBS`, `USAGE_STATS`, `BASE_DIR`, 全局变量）放在 `hyperframes_app.py` 中，通过 import 引用
3. 每个模块独立完成 + 跑通 `test_api.py` 后再拆下一个
4. `gunicorn` 在拆分期间持续运行，不影响线上服务

---

### Task 1: 创建 `api_templates.py` — 模板管理模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_templates.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`

**从 hyperframes_app.py 搬迁的函数:**
- `discover_templates()` (行385-408)
- `api_templates()` (行410-414)
- `api_template_detail(template_id)` (行415-419)
- `merge_config_with_user()` (行423-593) — *注意：这个函数被多个模块使用，需留在入口或被各模块共享*
- `api_save_template_config()` (行1807-1858)
- `api_get_template_config(template_id)` (行1859-1866)
- `api_create_template()` (行1870-2037)
- `api_delete_template()` (行2038-2078)
- `api_template_images()` (行4981-5000)
- `_get_template_images(template_id)` (行4966-4979)
- `_get_template(template_id)` (行838-843)
- `template_schema.json` 相关验证逻辑

**搬迁后 `api_templates.py` 结构:**

```python
"""api_templates.py — 模板管理模块（Blueprint）"""
from flask import Blueprint, request, jsonify
from pathlib import Path
import json, os, shutil, uuid

# 从入口模块导入共享变量
from hyperframes_app import BASE_DIR, TEMPLATES_DIR, logger

templates_bp = Blueprint('templates', __name__, url_prefix='/api')

# === 搬迁过来的所有函数 ===
# discover_templates()
# api_templates()
# api_template_detail()
# api_save_template_config()
# api_get_template_config()
# api_create_template()
# api_delete_template()
# api_template_images()
# _get_template_images()
# _get_template()

def register_routes(app):
    app.register_blueprint(templates_bp)
```

**在 `hyperframes_app.py` 中:**
- 删除搬迁的函数
- 添加导入: `from api_templates import register_routes as register_templates`
- 在 `app` 创建后调用: `register_templates(app)`

**测试验证:** 运行 `python3 test_api.py` 所有20项通过

- [ ] Step 1: 创建 `api_templates.py` 文件，搬迁所有模板相关函数
- [ ] Step 2: 修改 `hyperframes_app.py` — 删除搬迁的函数 + 添加 import 和注册
- [ ] Step 3: 启动gunicorn测试: 访问 `/api/templates` 返回正常
- [ ] Step 4: 运行 `python3 test_api.py` 全部通过
- [ ] Step 5: git commit

---

### Task 2: 创建 `api_video.py` — 视频渲染/生成/下载模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_video.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`
- Modify: `/home/agentuser/hyperframes_projects/api_templates.py` (如有交叉引用)

**从 hyperframes_app.py 搬迁的函数:**
- `render_video()` (行630-835)
- `api_batch_generate()` (行1629-1670)
- `api_preview()` (行1671-1696)
- `api_job_status(job_id)` (行1697-1703)
- `api_all_jobs()` (行1704-1720)
- `api_download(job_id)` (行1721-1749)
- `api_send_email()` (行1751-1805)
- `api_generate_copy()` (行845-921) — *注意：它用 `_get_template`, 需要从入口导入或 inline*
- `_generate_copy()` (行923-948)
- `_generate_copy_v2()` (行949-971)
- `_llm_copy_with_fallback()` (行972-1067)
- `_apply_golden_phrases()` (行1068-1114)
- `_gen_copy_general()` ~ `_gen_copy_farm()` (行1115-1627) — 所有模板的文案例
- `_gen_copy_variants()` (行2229-2468)
- `api_generate_variants()` (行2470-2492)
- `api_preview_data()` (行2494-2523)
- `api_preview_canvas()` (行2525-2775)
- `_get_font_size_for_style()` (行2776-2794)
- `_get_color_for_style()` (行2795-2825)
- `_smart_match_template()` (行2826-2879)
- `api_one_shot()` (行2882-2963)
- `api_one_shot_preview()` (行2965-3014)
- `api_one_shot_apply()` (行3016-3112)
- `api_v4_generate()` (行4552-4645)
- `api_preview_copy()` (行4455-4550)
- `api_generate_xiaohongshu_copy()` (行4647-4682)
- C任务相关: `queue_render()`, `process_queue()`, `api_queue_status()` (行4391-4421)
- 渲染引擎相关: `_update_progress()`, `_run_with_progress()` (行595-629)
- `api_stock_search()` (行4426-4454)
- `search_stock_images()` (行111-173)
- `cleanup_stale_jobs()`, `_stale_job_cleaner_loop()`, `_queue_timeout_check_loop()` (行174-231)
- `record_usage()`, `record_user_video()` (行244-292)
- `jobs_load_all()`, `jobs_save()`, `jobs_delete()`, `jobs_update_status()` (行294-382)
- `PRESET_STOCK_IMAGES` 和 `STOCK_KEYWORDS` (行33-110)

**注意:** `merge_config_with_user()` 被 `api_templates` 和 `api_video` 共用。建议留在 `hyperframes_app.py` 中或搬迁到 `shared.py`。

- [ ] Step 1: 创建 `api_video.py`，搬迁所有视频相关函数（这是最大的一块）
- [ ] Step 2: 处理共享依赖 — `merge_config_with_user` 等函数通过 import 引用
- [ ] Step 3: 修改 `hyperframes_app.py` — 删除搬迁的函数 + 添加 import 注册
- [ ] Step 4: 启动gunicorn测试: 访问 `/api/jobs` 和 `/api/templates` 正常
- [ ] Step 5: 运行 `python3 test_api.py` 全部通过
- [ ] Step 6: git commit

---

### Task 3: 创建 `api_user.py` — 用户/登录/授权模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_user.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`

**从 hyperframes_app.py 搬迁的函数:**
- `_init_users_db()` (行3413-3522)
- `ROLE_HIERARCHY` 常量及相关函数 (行3536-3591)
- `generate_api_key()`, `api_apikey_generate()` (行3594-3610)
- `check_daily_usage()` (行3611-3692)
- `require_role()`, `require_login()` (行3541-3592, 行3693-3713)
- `api_login()` (行3715-3769)
- `api_register()` (行3771-3806)
- `api_logout()` (行3808-3818)
- `api_me()` (行3819-3835)
- `api_user_videos()` (行3840-3875)
- `api_user_video_delete()` (行3876-3917)
- `api_invite_code()` (行3918-3932)
- `api_referral_record()` (行3934-3950)
- `api_referral_stats()` (行3951-3958)

- [ ] Step 1: 创建 `api_user.py`，搬迁所有用户相关函数
- [ ] Step 2: 修改 `hyperframes_app.py` 删除搬迁函数 + 注册
- [ ] Step 3: 测试登录流程: `curl -X POST ... /api/login`
- [ ] Step 4: 运行 `python3 test_api.py` 全部通过
- [ ] Step 5: git commit

---

### Task 4: 创建 `api_admin.py` — 管理后台模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_admin.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`

**从 hyperframes_app.py 搬迁的函数:**
- `api_admin_users()` (行3965-4009)
- `api_admin_user_role()` (行4010-4025)
- `api_admin_apikeys()` (行4026-4050)
- `api_admin_apikey_revoke()` (行4051-4063)
- `api_admin_template_create()` (行4070-4197)
- `api_admin_template_delete()` (行4198-4220)
- `api_admin_templates()` (行4221-4250)
- `api_admin_template_scenes(template_id)` (行4251-4337)
- `api_admin_usage()` (行4338-4390)
- `api_health()` (行2173-2187)
- `api_stats()` (行2189-2195)
- `api_disk_cleanup()` (行2196-2225)

- [ ] Step 1: 创建 `api_admin.py`，搬迁管理后台函数
- [ ] Step 2: 修改 `hyperframes_app.py` 注册
- [ ] Step 3: 运行 `python3 test_api.py` 全部通过
- [ ] Step 4: git commit

---

### Task 5: 创建 `api_bg.py` — 背景素材管理模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_bg.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`

**从 hyperframes_app.py 搬迁的函数:**
- `api_bg_categories()` (行4693-4709)
- `api_bg_category_create()` (行4710-4732)
- `api_bg_category_rename()` (行4733-4750)
- `api_bg_category_delete()` (行4751-4777)
- `api_bg_upload()` (行4779-4858)
- `api_bg_list()` (行4860-4894)
- `api_bg_reorder()` (行4895-4911)
- `api_bg_duration()` (行4912-4926)
- `api_bg_delete()` (行4927-4946)
- `serve_bg_upload(filename)` (行4948-4965)
- `api_upload()`, `api_list_uploads()`, `api_delete_upload()`, `serve_upload()` (行2080-2167)

- [ ] Step 1: 创建 `api_bg.py`，搬迁素材管理函数
- [ ] Step 2: 修改 `hyperframes_app.py` 注册
- [ ] Step 3: 运行 `python3 test_api.py` 全部通过
- [ ] Step 4: git commit

---

### Task 6: 创建 `api_wechat.py` — 微信推送/变体/裂变模块

**Files:**
- Create: `/home/agentuser/hyperframes_projects/api_wechat.py`
- Modify: `/home/agentuser/hyperframes_projects/hyperframes_app.py`

**从 hyperframes_app.py 搬迁的函数:**
- `api_push_wechat()` (行3125-3180)
- `api_variants()` (行3335-3346)
- `api_variant_config()` (行3347-3369)
- `_apply_variant_to_copy()` (行3371-3406)
- V4.5文案助手相关: `api_generate_copy()` 的后半部分(变体逻辑, 行3370+)
- 分享裂变: `api_referral_record()`, `api_referral_stats()` (已从 user 搬迁)

- [ ] Step 1: 创建 `api_wechat.py`
- [ ] Step 2: 修改 `hyperframes_app.py` 注册
- [ ] Step 3: 运行 `python3 test_api.py` 全部通过
- [ ] Step 4: git commit

---

## 第二阶段：前端优化（3个子任务）

### Task 7: 状态管理重构 — 全局变量 → `AppState`

**Files:**
- Modify: `/home/agentuser/hyperframes_projects/templates/index_v4_phone.html`

**目标:** 将散布的全局变量收敛到 `const AppState = { ... }` 单对象

**当前全局变量（行525-532）:**
```javascript
let user = null;
let template = null;
let templates = [];
let jobId = null;
let pollTimer = null;
let variants = [];
let variantIdx = 0;
let jobId_global = null;
```

**改为:**
```javascript
const AppState = {
    user: null,
    template: null,
    templates: [],
    jobId: null,
    pollTimer: null,
    variants: [],
    variantIdx: 0,
    _currentScreen: null,
    _origPollStatus: null
};

// 状态变更自动触发 UI 更新（可选）
```

**变更点:** 所有 `user` → `AppState.user`, `templates` → `AppState.templates` 等

- [ ] Step 1: 定义 `AppState` 对象，替换所有全局变量引用
- [ ] Step 2: 测试所有页面功能正常（登录、选模板、生成、进度、完成）
- [ ] Step 3: git commit

---

### Task 8: API 调用封装 — 统一错误处理

**Files:**
- Modify: `/home/agentuser/hyperframes_projects/templates/index_v4_phone.html`

**目标:** 所有 AJAX 请求走统一封装，消除重复 try/catch

**当前模式（重复出现~20次）:**
```javascript
fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)})
    .then(r => r.json())
    .then(d => { ... })
    .catch(e => toast('出错了'));
```

**改为:**
```javascript
async function apiCall(url, data = null, method = 'POST') {
    try {
        const r = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: data ? JSON.stringify(data) : undefined
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        return d;
    } catch(e) {
        toast(e.message || '网络异常');
        throw e;
    }
}

// 使用
const data = await apiCall('/api/one-shot-preview', {brand: '...'});
```

- [ ] Step 1: 添加 `apiCall()` 统一函数
- [ ] Step 2: 逐个替换所有 fetch 调用为 `apiCall()`
- [ ] Step 3: 测试所有 API 调用场景正常
- [ ] Step 4: git commit

---

### Task 9: UI/UX 体验优化

**Files:**
- Modify: `/home/agentuser/hyperframes_projects/templates/index_v4_phone.html`

**优化项:**
1. **骨架屏加载** — 模板列表、历史记录等数据加载时显示灰色骨架
2. **底部安全区** — iOS/Android 的 `env(safe-area-inset-bottom)` 适配
3. **加载状态** — 每个按钮自带 loading spinner（`<button loading>`）
4. **键盘弹出适配** — 表单输入时 `scrollIntoView`
5. **过渡动画** — 屏幕切换用 `translateX` / `fadeIn` CSS transition
6. **Toast 升级** — 支持不同类型的图标（成功/失败/警告）

- [ ] Step 1: 添加 CSS 过渡动画（~50行）
- [ ] Step 2: 添加骨架屏组件 + 按钮 loading 状态
- [ ] Step 3: 适配底部安全区 + 键盘弹出
- [ ] Step 4: 测试所有屏幕切换和加载状态
- [ ] Step 5: git commit

---

## 执行顺序

```
Phase 1 — 后端拆分
  Task 1: api_templates.py  ✓  -> test -> commit
  Task 2: api_video.py       -> test -> commit
  Task 3: api_user.py        -> test -> commit
  Task 4: api_admin.py       -> test -> commit
  Task 5: api_bg.py          -> test -> commit
  Task 6: api_wechat.py      -> test -> commit
  
Phase 2 — 前端优化
  Task 7: AppState 重构      -> test -> commit
  Task 8: apiCall 封装       -> test -> commit
  Task 9: UI/UX 优化         -> test -> commit
  
Phase 3 — 收尾
  全量 test_api.py 验证
  git push
```

每个 Task 执行期间 gunicorn 持续运行，线上服务不受影响。
