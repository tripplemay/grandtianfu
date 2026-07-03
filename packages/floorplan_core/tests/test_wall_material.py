# -*- coding: utf-8 -*-
"""墙面材质C (P2): 某面贴实拍参考图 (photo_id) 时, 语义提示让位 —— prompt 短语与轴测色块
都不再出 (由 img2img 参考图承载, 避免双重信号)。无 photo_id 时按材质A 照旧。"""
import json
import os

from floorplan_core import axon, geometry, prompt_gen

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # tests->pkg->packages->repo
DATA = os.path.join(REPO, "data", "projects", "D")


def _mini_G(walls: dict) -> dict:
    return {"rooms": [{"id": "r1", "type": "living", "rect": [0, 0, 400, 300],
                       "label": {"zh": "客厅"}, "walls": walls}]}


def test_prompt_clause_present_with_material_only():
    p = prompt_gen.generate([{"t": "sofa", "room_id": "r1", "dx": 10, "dy": 10}],
                            _mini_G({"N": {"material": "wood_panel"}}))
    assert "north wall clad in" in p


def test_prompt_clause_suppressed_when_photo_attached():
    p = prompt_gen.generate([{"t": "sofa", "room_id": "r1", "dx": 10, "dy": 10}],
                            _mini_G({"N": {"material": "wood_panel", "photo_id": "ph1"}}))
    assert "north wall clad in" not in p


def _load_D():
    G = geometry.load(os.path.join(DATA, "geometry.json"))
    geo = geometry.derive(G)
    geom = axon.geom_bundle(G, geo)
    furn = json.load(open(os.path.join(DATA, "furniture.json"), encoding="utf-8"))
    return G, geom, furn


def test_axon_tint_drawn_for_material_but_suppressed_for_photo():
    """轴测色块: 北墙有 material 时出 tint; 加 photo_id 后同一面不再出该 tint。"""
    G, geom, furn = _load_D()
    tint = axon.WALL_FINISH_TINT["wood_panel"]
    # geom_bundle 末位透传 G -> render 据此画/不画 tint (无 G= 形参)。
    # 北墙有 material -> 渲染出现 tint 色。
    G["rooms"][0]["walls"] = {"N": {"material": "wood_panel"}}
    with_mat = axon.render(axon.geom_bundle(G, geometry.derive(G)), furn, mode="photo")
    assert tint in with_mat
    # 同面加 photo_id -> tint 让位。
    G["rooms"][0]["walls"] = {"N": {"material": "wood_panel", "photo_id": "ph1"}}
    with_photo = axon.render(axon.geom_bundle(G, geometry.derive(G)), furn, mode="photo")
    assert tint not in with_photo
