# -*- coding: utf-8 -*-
"""P0-4 语义验收 semantic_accept: 盒外保真 + 盒内类别 (VLM 注入 mock, 无网络)。"""
import io

import numpy as np
from aigc import perspective, semantic_accept
from floorplan_core import catalog
from PIL import Image


def _synth_camera(f=1600.0, W=2048, H=1536):
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1.0]])
    eye = np.array([3000.0, 3000.0, 1450.0])
    fwd = np.array([10000.0, 12000.0, 0.0]) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    down /= np.linalg.norm(down)
    R = np.vstack([right, down, fwd])
    return perspective.Camera(K=K, R=R, t=-R @ eye), (W, H)


def _png(wh, color=(180, 170, 150)):
    buf = io.BytesIO()
    Image.new("RGB", wh, color).save(buf, format="PNG")
    return buf.getvalue()


_ROOMS = {"r": [0, 0, 2000, 2000]}
_FURN = [
    {"t": "sofa", "room_id": "r", "dx": 300, "dy": 600, "w": 210, "h": 90, "z": 800},
    {"t": "wine_cabinet", "room_id": "r", "dx": 400, "dy": 900, "w": 60, "h": 40, "z": 1400},
]


def _stub(responses):
    """按调用序返回 responses; 记录 messages。"""
    seq = list(responses)
    calls = []

    def chat_json(messages):
        calls.append(messages)
        return seq.pop(0) if len(seq) > 1 else seq[0]

    chat_json.calls = calls
    return chat_json


def test_outside_fidelity_flags_material_change():
    cam, wh = _synth_camera()
    chat = _stub([{"structure_preserved": False, "changes": ["地面大理石变木地板"]}])
    r = semantic_accept.check_outside_fidelity(_png(wh), _png(wh), chat)
    assert r["ok"] is False
    assert "木地板" in r["changes"][0]


def test_outside_fidelity_preserved_passes():
    cam, wh = _synth_camera()
    chat = _stub([{"structure_preserved": True, "changes": []}])
    r = semantic_accept.check_outside_fidelity(_png(wh), _png(wh), chat)
    assert r["ok"] is True


def test_box_categories_flags_wrong_furniture():
    cam, wh = _synth_camera()
    # 不变量 (c): 盒按面积降序, box 0 = 最大件 = sofa (210×90 > wine_cabinet 60×40)。
    chat = _stub([{"results": [{"box": 0, "is_expected": False, "actual": "书架"}]}])
    r = semantic_accept.check_box_categories(
        _png(wh), cam, _FURN, _ROOMS, wh, 10, chat, catalog=catalog
    )
    assert r["checked"] >= 1
    m = next(m for m in r["mismatches"] if m["actual"] == "书架")
    assert m["t"] == "sofa"  # box 序号 -> 家具类型映射正确 (非 wine_cabinet)


def test_box_categories_ignores_non_dict_result_item():
    """VLM 偶发在 results 里吐非 dict 项: 跳过它, 不连累同响应里的合法 mismatch (审查修复)。"""
    cam, wh = _synth_camera()
    chat = _stub([{"results": ["沙发画错了", {"box": 0, "is_expected": False, "actual": "书架"}]}])
    r = semantic_accept.check_box_categories(
        _png(wh), cam, _FURN, _ROOMS, wh, 10, chat, catalog=catalog
    )
    assert any(m["actual"] == "书架" for m in r["mismatches"])  # 合法项未被坏项连累


def test_box_categories_coerces_stringified_bool():
    """VLM 把布尔字符串化 (is_expected='false'): 仍判为不符 (审查修复 bool('false')==True 陷阱)。"""
    cam, wh = _synth_camera()
    chat = _stub([{"results": [{"box": 0, "is_expected": "false", "actual": "书架"}]}])
    r = semantic_accept.check_box_categories(
        _png(wh), cam, _FURN, _ROOMS, wh, 10, chat, catalog=catalog
    )
    assert any(m["actual"] == "书架" for m in r["mismatches"])


def test_box_categories_all_correct_no_mismatch():
    cam, wh = _synth_camera()
    chat = _stub([{"results": [{"box": 0, "is_expected": True}, {"box": 1, "is_expected": True}]}])
    r = semantic_accept.check_box_categories(
        _png(wh), cam, _FURN, _ROOMS, wh, 10, chat, catalog=catalog
    )
    assert r["mismatches"] == []


def test_evaluate_semantic_merges_both_checks():
    cam, wh = _synth_camera()
    chat = _stub([
        {"structure_preserved": False, "changes": ["墙面加了护墙板"]},  # fidelity fail
        {"results": [{"box": 0, "is_expected": False, "actual": "餐边柜"}]},  # category fail
    ])
    r = semantic_accept.evaluate_semantic(
        _png(wh), _png(wh), cam=cam, furniture=_FURN, rooms_by_id=_ROOMS,
        img_wh=wh, mm_per_px=10, chat_json=chat, catalog=catalog,
    )
    assert r["ok"] is False
    assert any("材质被改" in f for f in r["fail_reasons"])
    assert any("不是预期家具" in f for f in r["fail_reasons"])


def test_evaluate_semantic_degrades_on_vlm_exception():
    """VLM 抛异常 -> 该项跳过, 不阻断交付 (ok 不因异常变 False)。"""
    cam, wh = _synth_camera()

    def boom(messages):
        raise RuntimeError("vlm timeout")

    r = semantic_accept.evaluate_semantic(
        _png(wh), _png(wh), cam=cam, furniture=_FURN, rooms_by_id=_ROOMS,
        img_wh=wh, mm_per_px=10, chat_json=boom, catalog=catalog,
    )
    assert r["ok"] is True  # 全部降级跳过 -> 无 fail_reason
    assert r["checks"]["fidelity"]["skipped"]
    assert r["checks"]["categories"]["skipped"]


def test_evaluate_semantic_per_check_independent_degrade():
    """不变量 (b): 单项 VLM 异常只跳过该项 —— fidelity 抛错但 categories 仍报类别错。"""
    cam, wh = _synth_camera()
    n = [0]

    def chat(messages):
        n[0] += 1
        if n[0] == 1:  # 第一次 = fidelity: 抛错
            raise RuntimeError("fidelity timeout")
        return {"results": [{"box": 0, "is_expected": False, "actual": "书架"}]}

    r = semantic_accept.evaluate_semantic(
        _png(wh), _png(wh), cam=cam, furniture=_FURN, rooms_by_id=_ROOMS,
        img_wh=wh, mm_per_px=10, chat_json=chat, catalog=catalog,
    )
    assert r["checks"]["fidelity"]["skipped"]  # fidelity 降级跳过
    assert any("不是预期家具" in f for f in r["fail_reasons"])  # categories 仍生效
    assert r["ok"] is False


def test_box_categories_caps_and_reports_dropped():
    """超过 _MAX_BOXES 的盒记 dropped, 不静默截断。"""
    cam, wh = _synth_camera()
    many = [
        {"t": "cabinet", "room_id": "r", "dx": 200 + i * 60, "dy": 500, "w": 80, "h": 50, "z": 900}
        for i in range(semantic_accept._MAX_BOXES + 3)
    ]
    chat = _stub([{"results": []}])
    r = semantic_accept.check_box_categories(_png(wh), cam, many, _ROOMS, wh, 10, chat, catalog=catalog)
    assert r["checked"] <= semantic_accept._MAX_BOXES
    assert r["dropped"] >= 1
