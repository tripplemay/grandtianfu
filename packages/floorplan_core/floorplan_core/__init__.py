# -*- coding: utf-8 -*-
"""floorplan_core — 户型几何引擎 (单一真源).

子模块:
    geometry   纯函数核心: load / derive / validate / candidate_walls ...
    axon       等轴测 + 2D 平面渲染: render / render_plan_2d / from_geometry ...
    prompt_gen 由家具表 + 几何自动生成 4D 图生图提示词.

用法:
    from floorplan_core import geometry
    from floorplan_core import axon
    from floorplan_core import prompt_gen
    # 或直接用顶层 re-export:
    from floorplan_core import load, derive, render, render_plan_2d
"""
from . import geometry, axon, prompt_gen

# --- geometry 公共 API ---
from .geometry import (
    load,
    derive,
    validate,
    candidate_walls,
    merge_intervals,
    diff_intervals,
)

# --- axon 公共 API ---
from .axon import (
    render,
    render_plan_2d,
    resolve_furniture,
    from_geometry,
    geom_bundle,
    walls_for_engine,
    parse_geometry,
)

__all__ = [
    "geometry",
    "axon",
    "prompt_gen",
    "load",
    "derive",
    "validate",
    "candidate_walls",
    "merge_intervals",
    "diff_intervals",
    "render",
    "render_plan_2d",
    "resolve_furniture",
    "from_geometry",
    "geom_bundle",
    "walls_for_engine",
    "parse_geometry",
]
