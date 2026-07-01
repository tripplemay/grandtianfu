# -*- coding: utf-8 -*-
"""test_render_snapshot.py — 渲染快照安全网 (Phase0 收尾: render 字符串化护栏).

家具渲染本无独立 golden, 这是把"当前出图"钉成基线的安全网: 验证
render() / render_plan_2d() 返回的 SVG 字符串, 按各自落盘编码后, 与
.phase0-baseline/ 中仍应冻结的定稿 SVG **逐字节一致**。任何绘制顺序 / 格式 /
小数位漂移都会让本测试变红。

注意: photo 轴测包含家具。场景链路上线后, photo 会对贴墙家具做轴侧安全内缩,
不再用忽略目录里的历史 SVG 做逐字节锁死; 具体防穿墙坐标由 test_scene.py 覆盖。

数据真源 = data/projects/D/ 活几何 + 家具 (基线即由 build.py D 从此产出),
故快照必须用同一份活数据复现, 不读 fixtures (fixtures 与活数据已分叉)。

落盘编码对齐 (字节一致关键):
    plan2d  -> render_plan_2d, utf-8-sig (带 BOM, 历史落盘方式)
    photo   -> render(mode=photo), utf-8 (无 BOM)
    shell   -> render(mode=shell), utf-8 (无 BOM)

可独立运行:  python3 tests/test_render_snapshot.py   (退出码 0=PASS)
亦可 pytest:  pytest tests/test_render_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # tests -> floorplan_core(pkg) -> packages -> repo
DATA = os.path.join(REPO, "data", "projects")
BASELINE = os.path.join(REPO, ".phase0-baseline")

from floorplan_core import axon, geometry  # noqa: E402 (引擎库单一真源)

HOUSE = "D"
GEOM_JSON = os.path.join(DATA, HOUSE, "geometry.json")
FURN_JSON = os.path.join(DATA, HOUSE, "furniture.json")


def _load_inputs():
    G = geometry.load(GEOM_JSON)
    geo = geometry.derive(G)
    geom = axon.geom_bundle(G, geo)
    with open(FURN_JSON, encoding="utf-8") as fh:
        furniture = json.load(fh)
    return G, geo, geom, furniture


def _produce():
    """复现三种输出字节 (string 化路径: 不写文件, 仅取返回值再编码)."""
    G, geo, geom, furniture = _load_inputs()
    return {
        "平面布置图.svg": axon.render_plan_2d(G, geo, furniture).encode("utf-8-sig"),
        "D户型-照片底图.svg": axon.render(geom, furniture, mode="photo").encode("utf-8"),
        "D户型-空壳底图.svg": axon.render(geom, furniture, mode="shell").encode("utf-8"),
    }


def _baseline_bytes(name: str) -> bytes:
    with open(os.path.join(BASELINE, name), "rb") as fh:
        return fh.read()


@pytest.mark.parametrize("name", ["平面布置图.svg", "D户型-空壳底图.svg"])
def test_render_string_matches_baseline_byte_for_byte(name: str):
    produced = _produce()[name]
    expected = _baseline_bytes(name)
    assert produced == expected, (
        f"{name}: 渲染字符串与基线不逐字节一致 "
        f"(produced {len(produced)}B vs baseline {len(expected)}B)"
    )


def test_render_returns_string_without_out_path():
    """out_path 省略时必须返回非空 SVG 字符串 (string 化契约)."""
    G, geo, geom, furniture = _load_inputs()
    plan = axon.render_plan_2d(G, geo, furniture)
    photo = axon.render(geom, furniture, mode="photo")
    assert isinstance(plan, str) and plan.lstrip().startswith("<?xml")
    assert isinstance(photo, str) and photo.startswith("<svg")
    assert "1228.0,685.0" not in photo  # guard against leaking raw coord text assumptions


def test_out_path_still_writes_file(tmp_path):
    """向后兼容: 给 out_path 仍落盘, 且落盘内容 == 返回字符串 (对应编码)."""
    G, geo, geom, furniture = _load_inputs()
    p_plan = tmp_path / "plan.svg"
    p_photo = tmp_path / "photo.svg"
    svg_plan = axon.render_plan_2d(G, geo, furniture, str(p_plan))
    svg_photo = axon.render(geom, furniture, str(p_photo), mode="photo")
    assert p_plan.read_bytes() == svg_plan.encode("utf-8-sig")
    assert p_photo.read_bytes() == svg_photo.encode("utf-8")


def _main() -> int:
    produced = _produce()
    ok = True
    for name in ("平面布置图.svg", "D户型-空壳底图.svg"):
        same = produced[name] == _baseline_bytes(name)
        print("  [%s] %s (%dB)" % ("PASS" if same else "FAIL", name, len(produced[name])))
        ok = ok and same
    print("  [INFO] D户型-照片底图.svg uses scene clearance; see test_scene.py")
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
