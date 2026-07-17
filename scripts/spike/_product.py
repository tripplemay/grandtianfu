# -*- coding: utf-8 -*-
"""产品模块加载器 (calib-cure-b1 F011, spec §D5 spike 严格隔离)。

原则: **产品代码零改动、不 import main.py**。
  - 无包内依赖的纯模块 (perspective / catalog / plan2d_shapes) 用 importlib
    按文件路径加载 —— 不碰产品包结构, 与本批标定核查实验同方法;
  - aigc 包级模块 (providers / config / acceptance / eval_harness / raster) 内部有
    `from . import ...` 相对依赖, 无法按单文件路径加载 -> 把 apps/api 加入 sys.path
    后按包正常导入 (仍是只读消费, 明确不 import main.py)。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

# scripts/spike/_product.py -> parents[2] = 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_by_path(name: str, rel: str):
    """按仓库相对路径加载单文件模块 (注册进 sys.modules 供 dataclass 等机制使用)。"""
    path = REPO_ROOT / rel
    if not path.is_file():
        raise ImportError(f"产品文件不存在: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法从 {path} 构造模块 {name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_perspective():
    """apps/api/aigc/perspective.py (纯 numpy, 无包内依赖) —— Camera/_box_polys/
    annotate_boxes/_clip_face_near/NEAR_MM/_REAL_CEILING_MM/ANNO_* 的唯一来源。"""
    return _load_by_path("spike_perspective", "apps/api/aigc/perspective.py")


def load_catalog():
    """packages/floorplan_core/floorplan_core/catalog.py (纯 stdlib) ——
    plan2d_spec / CATALOG(en) / attach_en 的唯一来源。"""
    return _load_by_path("spike_catalog", "packages/floorplan_core/floorplan_core/catalog.py")


def load_plan2d_shapes():
    """packages/floorplan_core/floorplan_core/plan2d_shapes.py (纯 stdlib) ——
    edge/arms 部件的俯视几何解释器 (与产品 2D 外形同一套数学)。"""
    return _load_by_path(
        "spike_plan2d_shapes", "packages/floorplan_core/floorplan_core/plan2d_shapes.py"
    )


def import_aigc(mod_name: str):
    """按包导入 aigc 子模块 (providers/config/acceptance/eval_harness/raster)。

    只应在 run_ab 需要出图/量化时调用 (懒加载: --dry 干跑不触发 httpx 依赖)。
    """
    api_dir = str(REPO_ROOT / "apps" / "api")
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    return importlib.import_module(f"aigc.{mod_name}")
