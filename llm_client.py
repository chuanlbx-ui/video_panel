#!/usr/bin/env python3
"""
llm_client.py — DeepSeek API 封装
功能:
  1. llm_match_template: 自然语言 → 模板匹配 + 参数提取
  2. llm_optimize_copy:   模板参数 → 文案优化生成

API 调用健壮性: 超时 15s，失败优雅回退，不阻塞主流程。
"""

import json
import os
import re
import logging
from typing import Any

import requests
import yaml

logger = logging.getLogger(__name__)

# ──────────────────────── 配置加载 ────────────────────────

_CONFIG_CACHE: dict | None = None


def _load_config() -> dict:
    """加载 API 配置：优先从环境变量读取，其次从 config.yaml"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    # 优先从环境变量读取（无掩码问题）
    env_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    env_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

    if env_key and "..." not in env_key:
        _CONFIG_CACHE = {"api_key": env_key, "base_url": env_base_url.rstrip("/")}
        logger.info("LLM 客户端使用环境变量中的 API Key")
        return _CONFIG_CACHE

    # 其次从 config.yaml 读取
    config_path = os.path.expanduser("~/.hermes/config.yaml")
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as exc:
        logger.warning("无法读取配置文件 %s: %s", config_path, exc)
        _CONFIG_CACHE = {"api_key": "", "base_url": "https://api.deepseek.com/v1"}
        return _CONFIG_CACHE

    model_cfg = raw.get("model", {})
    api_key = model_cfg.get("api_key", "")
    base_url = model_cfg.get("base_url", "https://api.deepseek.com/v1")

    # 如果 config.yaml 中的 key 被掩码，清空
    if "..." in api_key:
        logger.warning("config.yaml 中的 api_key 疑似被截断/掩码，已忽略")
        api_key = ""

    _CONFIG_CACHE = {"api_key": api_key, "base_url": base_url.rstrip("/")}
    return _CONFIG_CACHE


def _deepseek_chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    timeout: int = 15,
) -> dict | None:
    """调用 DeepSeek Chat API，返回解析后的 JSON dict，失败返回 None"""
    cfg = _load_config()
    api_key = cfg["api_key"]
    base_url = cfg["base_url"]

    if not api_key or "..." in api_key:
        logger.warning("DeepSeek API key 无效或为掩码，跳过 API 调用")
        return None

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # 尝试提取 JSON（以防模型输出 markdown 围栏）
        return _extract_json(content)
    except requests.exceptions.Timeout:
        logger.error("DeepSeek API 超时 (%ss)", timeout)
    except requests.exceptions.RequestException as exc:
        logger.error("DeepSeek API 请求失败: %s", exc)
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        logger.error("DeepSeek API 响应解析失败: %s", exc)
    return None


def _extract_json(text: str) -> dict | None:
    """从文本中提取 JSON 对象（处理 markdown 围栏等）"""
    # 尝试 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 直接尝试解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 { 到最近的完整 } 截取
    start = text.find("{")
    if start >= 0:
        brace_depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                brace_depth += 1
            elif text[i] == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# ──────────────────── 模板描述映射 ────────────────────

_TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "food_promo": "餐饮饭店推广视频（火锅/中餐/小吃等行业，25秒，6场景：氛围开场→招牌→食材→故事→活动→行动）",
    "store_promo": "实体店铺推广视频（美发/美容/健身/家政等服务行业，18秒，5场景）",
    "event_invite": "活动邀请视频（开业/沙龙/展会/讲座等，15秒，4场景）",
    "personal_ip": "个人IP打造视频（创业者/专家/超级个体，20秒，3场景：我是谁→我能帮你→怎么找我）",
    "product_seed": "产品种草带货视频（实体产品/本地特产，18秒，4场景：痛点→产品→卖点→价格）",
    "farm_promo": "农产品推广视频（茶叶/蜂蜜/水果/山货等，突出原产地和品质）",
    "sanqi_industry": "三七产业推广视频（三七/中药材行业）",
    "association_invite": "协会入会邀请视频",
    "xinxue_course": "心学课程推广视频（国学/传统文化课程）",
    "xiaohongshu_style": "小红书风格种草视频（图文混排/生活分享风格）",
    "edu_recruit": "教育培训招生视频（学校/培训机构招生宣传）",
    "house_promo": "房产家居推广视频（楼盘/装修/家居展示）",
    "restaurant_promo_v1": "餐饮模板变体（另一种风格的餐饮宣传）",
    "store_promo_v1": "店铺模板变体（另一种风格的实体店推广）",
    "horizontal_promo": "横版视频（16:9宽屏，适合公众号/网站嵌入）",
    "ai_daily_video": "AI日报视频（科技资讯/每日速报风格）",
    "vertical_lixia": "立夏主题竖版视频（节气/节日主题）",
    "course_promo": "课程推广视频（在线课程/知识付费）",
}


# ──────────────────── 函数1: 模板匹配 ────────────────────


def llm_match_template(
    user_text: str,
    available_templates: list[dict] | None = None,
) -> dict[str, Any]:
    """
    解析用户自然语言，智能匹配视频模板并提取参数。

    参数:
        user_text: 用户输入的自然语言描述
            (e.g. "帮我做一条老张火锅店的宣传视频，做了十五年正宗重庆火锅")
        available_templates: 可选，模板列表（含 id/name/description）
            若为 None 则使用内置模板描述映射

    返回:
        dict 包含:
          - template_id: str       匹配的模板 ID
          - brand: str             品牌/店名/人名
          - description: str       描述/文案摘要
          - phone: str             电话号码（如无则为空字符串）
          - address: str           地址（如无则为空字符串）
          - value: str             价值主张/卖点（如无则为空字符串）
          - price: str             价格/优惠信息（如无则为空字符串）
    默认兜底: template_id="food_promo", 其余字段从原文提取。
    """
    # 构建模板列表描述
    if available_templates:
        template_lines = []
        for t in available_templates:
            tid = t.get("id", t.get("template_id", "?"))
            name = t.get("name", t.get("template_name", tid))
            desc = t.get("description", "")
            template_lines.append(f"- {tid}: {name} — {desc}")
        template_str = "\n".join(template_lines)
    else:
        template_str = "\n".join(
            f"- {tid}: {desc}" for tid, desc in _TEMPLATE_DESCRIPTIONS.items()
        )

    system_prompt = """你是一个视频模板匹配助手。根据用户的自然语言描述，从模板列表中选择最合适的模板，并提取关键参数。

请严格按照以下 JSON 格式返回（不要添加额外字段）：
{
  "template_id": "最匹配的模板ID",
  "brand": "品牌名/店名/人名（从用户输入提取）",
  "description": "一句话描述/核心卖点摘要（10-30字）",
  "phone": "电话号码（如未提及则为空字符串）",
  "address": "地址信息（如未提及则为空字符串）",
  "value": "价值主张/主打卖点（如未提及则为空字符串）",
  "price": "价格/优惠信息（如未提及则为空字符串）"
}

匹配原则：
1. 优先根据用户描述的行业/场景匹配对应模板
2. 如果用户明确说"做一条XX视频"，XX通常是品牌名
3. 描述要精炼，提取最有价值的卖点
4. 不要编造信息，未提及的字段留空字符串
5. 如果完全无法确定，默认选 food_promo"""

    user_prompt = f"""可用模板列表：
{template_str}

用户输入：
{user_text}

请返回匹配的 JSON。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = _deepseek_chat(messages)
    if result and isinstance(result, dict):
        # 验证并填充默认值
        return _normalize_match_result(result, user_text)

    # API 失败：回退到规则引擎
    logger.info("DeepSeek API 调用失败，回退到规则匹配")
    return _rule_based_match(user_text, available_templates)


def _normalize_match_result(result: dict, user_text: str) -> dict:
    """规范化 LLM 返回结果，确保所有字段存在"""
    defaults = {
        "template_id": "food_promo",
        "brand": "",
        "description": "",
        "phone": "",
        "address": "",
        "value": "",
        "price": "",
    }
    # 从 user_text 中尝试提取品牌名作为后备
    for key, default in defaults.items():
        if key not in result or not isinstance(result.get(key), str):
            result[key] = default

    # 如果 brand 为空，尝试从用户输入中提取第一个有意义的词
    if not result["brand"]:
        result["brand"] = _extract_brand_fallback(user_text)

    return result


def _extract_brand_fallback(text: str) -> str:
    """从用户文本中尝试提取品牌名"""
    patterns = [
        r"(?:帮|给|为)\s*(.+?)(?:的|作|做|拍|制作|宣传|推广)",
        r"(?:店名[是为：:]?\s*)(.+?)(?:[，。\s]|$)",
        r"(?:品牌[是为：:]?\s*)(.+?)(?:[，。\s]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return ""


# ──────────────────── 函数2: 文案优化 ────────────────────


def llm_optimize_copy(
    template_id: str,
    brand: str = "",
    desc: str = "",
    address: str = "",
    phone: str = "",
    value: str = "",
    price: str = "",
) -> dict[str, Any]:
    """
    根据模板类型和参数，生成/优化视频文案（场景文本+旁白）。

    参数:
        template_id: 模板 ID
        brand: 品牌/店名/人名
        desc: 描述/核心卖点
        address: 地址
        phone: 电话
        value: 价值主张
        price: 价格优惠信息

    返回:
        dict 包含:
          - scene_texts: list[dict]  每场景的文案 [{scene: 场景名, text: 文案}, ...]
          - voiceover_text: str      旁白/配音全文
          - slogan: str              标语/口号（可选）
    """
    system_prompt = """你是一个短视频文案优化专家。根据用户提供的模板类型和品牌信息，生成自然、有感染力、符合模板风格的视频文案。

请严格按照以下 JSON 格式返回：
{
  "scene_texts": [
    {"scene": "场景1名称", "text": "该场景显示文案"},
    {"scene": "场景2名称", "text": "该场景显示文案"},
    ...
  ],
  "voiceover_text": "完整的配音旁白文本（所有场景串联成一段自然流畅的配音）",
  "slogan": "一句话标语/口号"
}

文案风格要求：
- 餐饮模板: 温暖、有烟火气，突出食材和匠心
- 店铺模板: 专业、亲切，突出服务和环境
- 个人IP: 真诚、有力量，突出个人价值和差异化
- 产品种草: 种草感，突出痛点和解决方案
- 活动邀约: 有紧迫感和仪式感
- 教育培训: 权威感和成长感
- 农产品: 质朴、原生态、真实感
- 其他类型: 贴合行业特点

字数控制：每场景文案不超过20字，旁白全文50-120字。"""

    user_prompt = f"""模板 ID: {template_id}
品牌: {brand}
描述: {desc}
地址: {address}
电话: {phone}
价值主张: {value}
价格/优惠: {price}

请根据模板类型生成匹配的文案。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = _deepseek_chat(messages, temperature=0.4, max_tokens=2048)
    if result and isinstance(result, dict):
        return _normalize_copy_result(result, template_id, brand, desc, address, phone)

    # API 失败：回退到模板默认文案
    logger.info("DeepSeek API 文案优化失败，回退到默认文案")
    return _rule_based_copy(template_id, brand, desc, address, phone, value, price)


def _normalize_copy_result(result: dict, template_id: str, brand: str,
                           desc: str, address: str, phone: str) -> dict:
    """规范化文案优化结果"""
    defaults = {
        "scene_texts": [],
        "voiceover_text": "",
        "slogan": "",
    }
    for key, val in defaults.items():
        if key not in result:
            result[key] = val
    # 确保 scene_texts 是列表
    if not isinstance(result.get("scene_texts"), list):
        result["scene_texts"] = []
    return result


# ──────────────────── 规则引擎回退 ────────────────────


def _rule_based_match(
    user_text: str,
    available_templates: list[dict] | None = None,
) -> dict[str, Any]:
    """基于简单关键词的规则匹配回退"""
    text_lower = user_text.lower()

    # 关键词 → template_id 映射
    keyword_map: list[tuple[list[str], str]] = [
        (["火锅", "餐饮", "饭店", "餐厅", "美食", "食堂", "小吃", "厨房", "吃", "菜", "食", "老店"], "food_promo"),
        (["美发", "美容", "理发", "健身", "家政", "spa", "按摩", "养生", "实体店", "店铺"], "store_promo"),
        (["开业", "沙龙", "展会", "讲座", "活动", "邀约", "邀请", "庆典", "促销活动"], "event_invite"),
        (["个人", "ip", "创业", "创始人", "我是谁", "个人品牌", "超级个体"], "personal_ip"),
        (["种草", "产品", "带货", "商品", "特产", "推荐好物", "好物"], "product_seed"),
        (["茶叶", "蜂蜜", "水果", "山货", "农产品", "农", "果园", "种植"], "farm_promo"),
        (["三七", "药材", "中药材", "中药"], "sanqi_industry"),
        (["协会", "入会", "会员", "商会"], "association_invite"),
        (["心学", "国学", "传统文化", "王阳明", "课程"], "xinxue_course"),
        (["小红书", "笔记", "种草"], "xiaohongshu_style"),
        (["教育", "培训", "招生", "学校", "培训", "学习"], "edu_recruit"),
        (["房产", "楼盘", "装修", "家居", "买房", "租房", "房地产"], "house_promo"),
        (["横版", "横屏", "16:9", "公众号"], "horizontal_promo"),
        (["ai日报", "科技", "每日", "日报", "资讯"], "ai_daily_video"),
        (["立夏", "节气", "节日", "主题"], "vertical_lixia"),
        (["课程", "教", "网课", "知识付费", "线上课"], "course_promo"),
    ]

    matched_tid = "food_promo"
    max_score = 0
    for keywords, tid in keyword_map:
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > max_score:
            max_score = score
            matched_tid = tid

    # 尝试提取品牌/店名
    brand = _extract_brand_fallback(user_text)

    # 尝试提取电话
    phone = ""
    phone_match = re.search(r"(1[3-9]\d{9})", user_text)
    if phone_match:
        phone = phone_match.group(1)

    # 尝试提取地址
    address = ""
    addr_match = re.search(r"(?:地址[：:]\s*|位于|在)(.+?)(?:[。，]|\d{11}|$)", user_text)
    if addr_match:
        address = addr_match.group(1).strip()

    # 提取价格
    price = ""
    price_match = re.search(r"(\d+[./]?\d*\s*[元折折扣价])", user_text)
    if price_match:
        price = price_match.group(1)

    return {
        "template_id": matched_tid,
        "brand": brand,
        "description": user_text[:60] if len(user_text) > 60 else user_text,
        "phone": phone,
        "address": address,
        "value": "",
        "price": price,
    }


def _rule_based_copy(
    template_id: str,
    brand: str,
    desc: str,
    address: str,
    phone: str,
    value: str,
    price: str,
) -> dict[str, Any]:
    """基于模板类型的默认文案生成"""
    brand_display = brand if brand else "我们"

    # 按模板类型生成默认文案
    if template_id in ("food_promo", "restaurant_promo_v1"):
        scenes = [
            {"scene": "氛围开场", "text": f"{brand_display}，做了这么多年"},
            {"scene": "招牌展示", "text": f"{desc}" if desc else "招牌推荐，老顾客都说好"},
            {"scene": "食材理念", "text": "精选食材，用心做好每一餐"},
            {"scene": "活动信息", "text": f"{price}" if price else "欢迎进店品尝"},
            {"scene": "号召行动", "text": f"{address}" if address else "期待您的光临"},
        ]
        voiceover = f"{brand_display}。{desc}。{'地址：' + address + '。' if address else ''}{'电话：' + phone + '。' if phone else ''}欢迎您来品尝。"
        slogan = "用心做菜，等你来尝"

    elif template_id in ("store_promo", "store_promo_v1"):
        scenes = [
            {"scene": "温馨开场", "text": f"千挑万选，不如来{brand_display}"},
            {"scene": "环境展示", "text": "舒适干净·专业服务"},
            {"scene": "服务介绍", "text": "每一处细节都不将就"},
            {"scene": "客户好评", "text": "来过的人都说好"},
            {"scene": "行动号召", "text": f"{address}" if address else "欢迎预约体验"},
        ]
        voiceover = f"{brand_display}，舒适干净的环境，专业贴心的服务。{desc}。{'地址：' + address + '。' if address else ''}{'电话：' + phone + '。' if phone else ''}欢迎你来体验。"
        slogan = "匠心服务，品质之选"

    elif template_id == "personal_ip":
        scenes = [
            {"scene": "我是谁", "text": f"你好，我是{brand_display}"},
            {"scene": "我能帮你", "text": f"{desc}" if desc else "专注这个领域，为你提供专业服务"},
            {"scene": "怎么找我", "text": f"{phone}" if phone else "期待与你合作"},
        ]
        voiceover = f"你好，我是{brand_display}。{desc}。期待与你交流合作。"
        slogan = "专业·专注·值得信赖"

    elif template_id == "event_invite":
        scenes = [
            {"scene": "大标题", "text": f"{desc}" if desc else "盛大活动，诚邀莅临"},
            {"scene": "活动信息", "text": f"{brand_display}"},
            {"scene": "活动亮点", "text": f"{value}" if value else "精彩内容，不容错过"},
            {"scene": "参与方式", "text": f"{phone}" if phone else "立即报名"},
        ]
        voiceover = f"{brand_display}，{desc}。{'地址：' + address + '。' if address else ''}诚邀您的莅临。"
        slogan = "期待您的到来"

    elif template_id == "product_seed":
        scenes = [
            {"scene": "痛点", "text": f"{desc}" if desc else "你有这个烦恼吗？"},
            {"scene": "产品亮相", "text": f"{brand_display}，为你而来"},
            {"scene": "卖点", "text": f"{value}" if value else "品质保证，值得拥有"},
            {"scene": "价格购买", "text": f"{price}" if price else "限时优惠中"},
        ]
        voiceover = f"你还在{desc}吗？试试{brand_display}吧。{value if value else ''}{'仅需' + price + '。' if price else ''}赶快入手吧。"
        slogan = "好物不等人"

    elif template_id == "farm_promo":
        scenes = [
            {"scene": "原产地", "text": f"来自{brand_display}" if brand else "原产地直供"},
            {"scene": "品质展示", "text": f"{desc}" if desc else "天然无添加，大自然的味道"},
            {"scene": "匠心故事", "text": "从田间到餐桌，品质看得见"},
            {"scene": "购买方式", "text": f"{phone}" if phone else "欢迎订购"},
        ]
        voiceover = f"{brand_display}。{desc}。天然品质，产地直发。{'联系电话：' + phone + '。' if phone else ''}"
        slogan = "大自然的馈赠"

    elif template_id == "edu_recruit":
        scenes = [
            {"scene": "开篇", "text": f"想学{brand_display if brand else '新技能'}？来这里"},
            {"scene": "课程展示", "text": f"{desc}" if desc else "专业课程，名师指导"},
            {"scene": "学员见证", "text": "学有所成，未来可期"},
            {"scene": "招生信息", "text": f"{phone}" if phone else "名额有限，立即报名"},
        ]
        voiceover = f"{brand_display}，{desc}。专业课程，名师指导。{'联系电话：' + phone + '。' if phone else ''}"
        slogan = "学有所成，成就未来"

    else:
        # 通用兜底
        scenes = [
            {"scene": "开场", "text": f"{brand_display}" if brand else "你好"},
            {"scene": "介绍", "text": f"{desc}" if desc else "为你提供优质服务"},
            {"scene": "联系方式", "text": f"{phone}" if phone else "期待您的联系"},
        ]
        voiceover = f"{brand_display}。{desc}。{'地址：' + address + '。' if address else ''}{'电话：' + phone + '。' if phone else ''}"
        slogan = "品质服务，值得信赖"

    return {
        "scene_texts": scenes,
        "voiceover_text": voiceover,
        "slogan": slogan,
    }


# ──────────────────── 快速测试 ────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 50)
    print("测试 llm_match_template")
    print("=" * 50)

    test_inputs = [
        "帮我做一条老张火锅店的宣传视频，做了十五年正宗重庆火锅",
        "帮我做一条小王美发店的推广视频，专业美发十年老店",
        "我们下周六在会展中心有个教育展会，帮我做个邀请视频",
        "帮我个人IP打造的视频，我是李老师，做国学培训的",
        "帮我推广一下我们村的山货，土蜂蜜和野生菌",
        "店铺新开业，做个开业活动邀请视频",
    ]

    for inp in test_inputs:
        print(f"\n输入: {inp}")
        result = llm_match_template(inp)
        print(f"输出: {json.dumps(result, ensure_ascii=False, indent=2)}")

    print("\n" + "=" * 50)
    print("测试 llm_optimize_copy")
    print("=" * 50)

    copy_result = llm_optimize_copy(
        template_id="food_promo",
        brand="老张火锅",
        desc="做了十五年正宗重庆火锅",
        address="重庆市渝中区解放碑88号",
        phone="13800138000",
        value="正宗重庆味，手工炒料",
        price="全场八折",
    )
    print(f"输出: {json.dumps(copy_result, ensure_ascii=False, indent=2)}")
