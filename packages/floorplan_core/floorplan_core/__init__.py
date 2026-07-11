# -*- coding: utf-8 -*-
"""floorplan_core — 户型几何引擎 (单一真源).

子模块:
    geometry   纯函数核心: load / derive / validate / candidate_walls ...
    axon       等轴测 + 2D 平面渲染: render / render_plan_2d / from_geometry ...
    scene      结构化渲染场景: build_scene / validate_scene / render_manifest ...
    prompt_gen 由家具表 + 几何自动生成 4D 图生图提示词.
    catalog    家具受控目录 + 默认外观 (Phase1.5a; AI 选型/expand 填外观).
    room_brief 逐房简报 (尺寸/门窗/可选家具), 喂 AI 摆家具 LLM.
    lint       布局质量体检: lint_layout (悬空/背贴落地窗/家具碰撞), 出图前可降级门禁.

用法:
    from floorplan_core import geometry
    from floorplan_core import axon
    from floorplan_core import prompt_gen
    # 或直接用顶层 re-export:
    from floorplan_core import load, derive, render, render_plan_2d
"""
from . import geometry, axon, prompt_gen, catalog, room_brief, scene, lint

# --- lint 公共 API ---
from .lint import lint_layout

# --- geometry 公共 API ---
from .geometry import (
    load,
    derive,
    validate,
    candidate_walls,
    merge_intervals,
    diff_intervals,
    merge_groups,
    room_group_of,
    group_rep_map,
    nearest_part,
)

# --- axon 公共 API ---
from .axon import (
    render,
    render_plan_2d,
    resolve_furniture,
    build_scene,
    validate_scene as validate_render_scene,
    render_manifest,
    from_geometry,
    geom_bundle,
    walls_for_engine,
    parse_geometry,
)

__all__ = [
    "geometry",
    "axon",
    "prompt_gen",
    "catalog",
    "room_brief",
    "scene",
    "lint",
    "lint_layout",
    "load",
    "derive",
    "validate",
    "candidate_walls",
    "merge_intervals",
    "diff_intervals",
    "merge_groups",
    "room_group_of",
    "group_rep_map",
    "nearest_part",
    "render",
    "render_plan_2d",
    "resolve_furniture",
    "build_scene",
    "validate_render_scene",
    "render_manifest",
    "from_geometry",
    "geom_bundle",
    "walls_for_engine",
    "parse_geometry",
]
