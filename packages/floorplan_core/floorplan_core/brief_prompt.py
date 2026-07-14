# -*- coding: utf-8 -*-
"""结构化设计 Brief -> 紧凑提示词片段 (工作流改造 B3)。

Brief 是把自由文本需求结构化 (风格方向/预算/主材/主色/禁忌/重点房间等), 由此编译出一段
确定性的英文指令片段, 供轴测 (prompt_gen.generate) 与实拍 (_real_render_prompt) 两条链复用。
None/空 -> 空串 (贯通点在 style 为空时逐字节等价旧输出, 保护历史基线)。

Brief 字段 (全部可选):
  occupants          str   居住人群
  budget_tier        str   预算档位
  style_direction    str   风格方向
  primary_materials  [str] 主材
  banned_materials   [str] 禁用材质
  primary_colors     [str] 主色
  banned_colors      [str] 禁用颜色
  keep_hardscape     bool  保留硬装/建筑 (True 时加一句硬装保护)
  focus_rooms        [str] 重点房间
  avoid_elements     [str] 不希望出现的元素
  decor_preferences  [str] 配饰偏好 (decor-b2: 多/少配饰、偏好挂画/绿植/摆件等)
"""
from __future__ import annotations

from typing import Any, Optional

# 编译顺序固定 (确定性输出, 便于测试与复现)。
_STR_FIELDS = (
    ("occupants", "target residents"),
    ("budget_tier", "budget tier"),
    ("style_direction", "style direction"),
)
_LIST_FIELDS = (
    ("primary_materials", "preferred materials"),
    ("banned_materials", "avoid materials"),
    ("primary_colors", "preferred colors"),
    ("banned_colors", "avoid colors"),
    ("focus_rooms", "focus rooms"),
    ("avoid_elements", "avoid"),
    ("decor_preferences", "soft furnishing preferences"),  # decor-b2 配饰偏好
)


def _clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def compile_brief(brief: Optional[dict]) -> str:
    """把结构化 Brief 编译为一段紧凑的英文指令片段; None/空/无有效字段时返回空串。"""
    if not isinstance(brief, dict):
        return ""
    segments: list[str] = []
    # 字符串字段
    for key, label in _STR_FIELDS:
        text = _clean_str(brief.get(key))
        if text:
            segments.append(f"{label}: {text}")
    # keep_hardscape 紧跟 style_direction 之后 (硬装保护语义上属风格约束)。
    if bool(brief.get("keep_hardscape")):
        segments.append("keep the existing hardscape and architecture unchanged")
    # 列表字段
    for key, label in _LIST_FIELDS:
        vals = _clean_list(brief.get(key))
        if vals:
            segments.append(f"{label}: {', '.join(vals)}")
    if not segments:
        return ""
    return "Design brief — " + "; ".join(segments) + "."
