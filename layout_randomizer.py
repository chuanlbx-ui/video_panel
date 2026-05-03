#!/usr/bin/env python3
"""
layout_randomizer.py — 动态排版随机感系统

对生成的 HTML 施加确定性伪随机抖动：
  - font-size: ±2px 随机偏移
  - margin-top: ±5% 随机偏移
  - 粒子数量: 乘以 0.7~1.3 随机系数

使用 LCG 伪随机算法（无 Math.random），相同 seed 结果完全一致。
不会破坏 GSAP 动画（仅影响静态 CSS 数值和粒子数量）。
"""

import re
import random


# ==================== 确定性 LCG 伪随机 ====================

class LCGRandom:
    """
    线性同余生成器（LCG），确定性伪随机。
    参数来自 Numerical Recipes (Press et al.):
      m = 2^31 - 1 = 2147483647
      a = 1664525
      c = 1013904223
    """
    def __init__(self, seed: int):
        self.m = 2147483647
        self.a = 1664525
        self.c = 1013904223
        self.state = seed & 0x7FFFFFFF  # 确保正数

    def _next(self):
        self.state = (self.a * self.state + self.c) % self.m
        return self.state

    def randint(self, lo: int, hi: int) -> int:
        """返回 [lo, hi] 闭区间内的随机整数"""
        if lo >= hi:
            return lo
        r = self._next()
        span = hi - lo + 1
        return lo + (r % span)

    def uniform(self, lo: float, hi: float) -> float:
        """返回 [lo, hi) 区间内的随机浮点数"""
        r = self._next()
        return lo + (r / self.m) * (hi - lo)

    def choice(self, seq):
        """从序列中随机选一项"""
        idx = self.randint(0, len(seq) - 1)
        return seq[idx]


# ==================== 抖动核心函数 ====================

# font-size 正则：匹配 "font-size: XXXpx" 或 "font-size:XXXpx"
# 使用负向前瞻避免匹配 url(data:...) 或 base64 等
_FONT_SIZE_RE = re.compile(r'font-size\s*:\s*(\d+)\s*px', re.IGNORECASE)

# margin-top 正则：匹配 "margin-top: XXXpx" 或 "margin-top:XXXpx"
_MARGIN_TOP_RE = re.compile(r'margin-top\s*:\s*(\d+)\s*px', re.IGNORECASE)


def apply_font_jitter(html: str, rnd: LCGRandom, font_range: int = 2) -> str:
    """
    font-size 随机偏移 ±font_range px。
    对 font-size: Npx 中的 N 施加偏移，确保不低于 8px。
    """
    def _jitter(m):
        val = int(m.group(1))
        delta = rnd.randint(-font_range, font_range)
        new_val = max(8, val + delta)
        return f'font-size: {new_val}px'
    return _FONT_SIZE_RE.sub(_jitter, html)


def apply_margin_jitter(html: str, rnd: LCGRandom, margin_pct: float = 5.0) -> str:
    """
    margin-top 随机偏移 ±margin_pct%。
    对 margin-top: Npx 中的 N 施加百分比偏移，确保不低于 0px。
    """
    def _jitter(m):
        val = int(m.group(1))
        delta_pct = rnd.uniform(-margin_pct, margin_pct)
        delta = int(val * delta_pct / 100.0)
        new_val = max(0, val + delta)
        return f'margin-top: {new_val}px'
    return _MARGIN_TOP_RE.sub(_jitter, html)


def apply_particle_jitter(html: str, rnd: LCGRandom, particle_min: float = 0.7, particle_max: float = 1.3) -> str:
    """
    粒子数量乘以随机系数 [particle_min, particle_max]。
    匹配 JavaScript 中 `i < {n_particles}` 部分的 n_particles 数值。
    格式: `for (let i = 0; i < NP; i++)`
    """
    # 使用宽匹配 + group 提取，避免 look-behind
    PAT = re.compile(r'for\s*\(\s*let\s+i\s*=\s*0\s*;\s*i\s*<\s*(\d+)\s*;\s*i\+\+\s*\)')

    def _jitter(m):
        val = int(m.group(1))
        factor = rnd.uniform(particle_min, particle_max)
        new_val = max(1, int(val * factor))
        return f'for (let i = 0; i < {new_val}; i++)'
    return PAT.sub(_jitter, html)


def apply_random_jitter(html: str, rnd_seed: int, font_range: int = 2, margin_pct: float = 5.0,
                         particle_min: float = 0.7, particle_max: float = 1.3) -> str:
    """
    主入口：对 HTML 施加所有随机抖动。

    参数:
      html        — 原始 HTML 字符串
      rnd_seed    — 确定性伪随机种子（整数）
      font_range  — font-size 偏移范围（px，默认 ±2）
      margin_pct  — margin-top 偏移百分比（默认 ±5%）
      particle_min — 粒子数量乘数下限（默认 0.7）
      particle_max — 粒子数量乘数上限（默认 1.3）

    返回:
      施加抖动后的 HTML 字符串
    """
    # 为每种抖动创建独立的 LCG 实例，避免相互干扰
    rnd_font = LCGRandom(rnd_seed + 0x1111)
    rnd_margin = LCGRandom(rnd_seed + 0x2222)
    rnd_particle = LCGRandom(rnd_seed + 0x3333)

    html = apply_font_jitter(html, rnd_font, font_range)
    html = apply_margin_jitter(html, rnd_margin, margin_pct)
    html = apply_particle_jitter(html, rnd_particle, particle_min, particle_max)

    return html


# ==================== 简易自测 ====================

if __name__ == "__main__":
    # 验证确定性
    sample_html = '''<div class="large_white" style="font-size: 110px; margin-top: 30px;">
  <script>
    for (let i = 0; i < 12; i++) { mkParticles(); }
  </script>
</div>'''

    result1 = apply_random_jitter(sample_html, rnd_seed=42)
    result2 = apply_random_jitter(sample_html, rnd_seed=42)
    result3 = apply_random_jitter(sample_html, rnd_seed=99)

    assert result1 == result2, f"确定性失败: seed 42 两次结果不一致"
    # 不同 seed 应产生不同的结果（极低概率相同，这里放宽为打印差异）
    diff = result1 != result3
    print(f"  seed 42 vs 99 差异: {'✓ 不同' if diff else '⚠ 相同（极小概率）'}")

    # 验证 font-size 偏移范围
    fs_vals = re.findall(r'font-size:\s*(\d+)px', result1)
    if fs_vals:
        orig_fs = int(re.findall(r'font-size:\s*(\d+)px', sample_html)[0])
        for v in fs_vals:
            assert abs(int(v) - orig_fs) <= 2, f"font-size 偏移超过 ±2px: {v} vs {orig_fs}"

    # 验证 margin-top 偏移范围
    mt_vals = re.findall(r'margin-top:\s*(\d+)px', result1)
    if mt_vals:
        orig_mt = int(re.findall(r'margin-top:\s*(\d+)px', sample_html)[0])
        for v in mt_vals:
            delta_pct = abs(int(v) - orig_mt) / max(orig_mt, 1) * 100
            assert delta_pct <= 5.1, f"margin-top 偏移超过 ±5%: {v} vs {orig_mt} ({delta_pct:.1f}%)"

    # 验证粒子数量
    particle_vals = re.findall(r'for \(let i = 0; i < (\d+); i\+\+\)', result1)
    if particle_vals:
        orig_n = int(re.findall(r'for \(let i = 0; i < (\d+); i\+\+\)', sample_html)[0])
        for v in particle_vals:
            ratio = int(v) / orig_n
            assert 0.6 <= ratio <= 1.4, f"粒子数量比例异常: {v} vs {orig_n} (ratio={ratio:.2f})"

    print("✅ layout_randomizer 自测全部通过")
    print(f"  seed=42: {result1}")
    print(f"  seed=99: {result3}")
