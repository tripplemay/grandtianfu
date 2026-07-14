# -*- coding: utf-8 -*-
"""decor-b1 F005: 附着配饰 decor 子列表的写边界校验 + 存取往返无损。"""
import main
from floorplan_core import catalog


def _base(**extra):
    it = {"t": "sofa", "room_id": "r_live", "dx": 10, "dy": 10, "w": 210, "h": 90, "orient": "N"}
    it.update(extra)
    return [it]


def test_validate_accepts_valid_decor():
    assert main._furniture_items_error(_base(decor=[{"t": "cushions"}])) is None
    # 宿主不兼容仍放行 (软校验, 渲染期剥离)
    assert main._furniture_items_error(_base(decor=[{"t": "bedding"}])) is None
    # 无 decor 键 / 空 decor 均合法
    assert main._furniture_items_error(_base()) is None
    assert main._furniture_items_error(_base(decor=[])) is None


def test_validate_rejects_malformed_decor():
    # decor 非数组
    assert main._furniture_items_error(_base(decor={"t": "cushions"})) is not None
    # 元素非对象
    assert main._furniture_items_error(_base(decor=["cushions"])) is not None
    # 未注册配饰类型
    assert main._furniture_items_error(_base(decor=[{"t": "nope"}])) is not None
    assert main._furniture_items_error(_base(decor=[{"t": "sofa"}])) is not None  # 家具非配饰


def test_expand_preserves_decor_roundtrip():
    """catalog.expand (存取路径补外观) 不丢弃 decor 子列表。"""
    items = [{"t": "sofa", "room_id": "r_live", "dx": 10, "dy": 10,
              "decor": [{"t": "cushions"}]}]
    out = catalog.expand(items)
    assert out[0]["decor"] == [{"t": "cushions"}]
    assert "w" in out[0]  # 外观已补
