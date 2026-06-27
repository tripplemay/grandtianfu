# -*- coding: utf-8 -*-
"""setuptools shim — 兼容旧版 pip (<21.3, 无 PEP 660 editable 支持).

权威元数据在 pyproject.toml; 此处仅为旧 pip `pip install -e` 提供 setup.py 入口.
新版 pip 仍优先使用 pyproject.toml。
"""
from setuptools import setup

setup(
    name="floorplan_core",
    version="0.1.0",
    description="户型几何引擎 (geometry derive + 等轴测/2D 平面渲染) — 单一真源",
    python_requires=">=3.9",
    packages=["floorplan_core"],
)
