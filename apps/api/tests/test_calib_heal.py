# -*- coding: utf-8 -*-
"""存量标定自愈 calib_heal.py (calib-z-b1 F002): 重跑原始输入 -> 正确 camera, 幂等且不误伤。

本文件全程纯内存 (heal_photos 是纯函数, 无文件 I/O) -> 结构上不可能写穿 git-tracked 的
data/projects (render-fix-b1 R4 教训)。生产载荷来自只读取回的 fixture。
"""

import copy
import json
import pathlib

import numpy as np
from aigc import calib_heal, perspective

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# v1/v6/v7 三个 baseline 实测一致 (见 test_perspective._PROD_ROOM_RECTS)
_ROOM_RECTS = {
    "r_live": [495, 580, 720, 830],
    "r_master": [1215, 1020, 600, 390],
    "r_cloak": [1215, 760, 300, 260],
    "r_garden": [410, 0, 310, 250],
}

# 「z 朝上但平面被镜像」的解 —— 自愈后地面预期移动 (裁决 #3:A/#4:A), 须 F003 目检定论
_MIRRORED = {"dabcb951390546d8a118a90e02940e30", "1537e6d839504230972de8a05ee98c8f"}


def _prod_photos() -> list[dict]:
    """把只读取回的生产标定 fixture 还原成 photos.json 的形状。"""
    doc = json.loads((_FIXTURES / "prod_calibrations.json").read_text())
    return [
        {
            "id": e["photo_id"],
            "room_id": e["room_id"],
            "calibration": {
                "img_wh": e["img_wh"],
                "x_lines": e["x_lines"],
                "y_lines": e["y_lines"],
                "anchors": e["anchors"],
                "camera": e["stored_camera"],
            },
        }
        for e in doc["entries"]
    ]


def _heal(photos):
    return calib_heal.heal_photos(photos, room_rects=_ROOM_RECTS)


def test_stored_production_cameras_are_defective_positive_control():
    """阳性对照: 先证存量确实带病, 否则下面的自愈断言是空转。"""
    photos = _prod_photos()
    below = [p for p in photos if calib_heal.camera_height_mm(p["calibration"]["camera"]) <= 0]
    assert len(photos) == 11, "生产全量 11 条 (v1x1 + v6x5 + v7x5)"
    assert len(below) == 7, f"存量应有 7 条相机在地板下方 (物理不可能), 实得 {len(below)}"


def test_heal_puts_every_production_camera_above_the_floor():
    healed, report = _heal(_prod_photos())
    assert all(
        calib_heal.camera_height_mm(p["calibration"]["camera"]) > 0 for p in healed
    ), "自愈后 11/11 相机必须在地板上方"
    s = calib_heal.summarize(report)
    assert s["camera_below_floor_before"] == 7
    assert s["camera_below_floor_after"] == 0


def test_heal_is_idempotent():
    """幂等: 对已自愈的数据再跑一次 -> 全部 unchanged, 零改写。"""
    once, _ = _heal(_prod_photos())
    twice, report2 = _heal(once)
    assert {e["status"] for e in report2} == {"unchanged"}, "二次自愈不得再改写"
    assert twice == once, "二次自愈结果必须完全一致"


def test_heal_does_not_mutate_its_input():
    """纯函数: 不得就地改入参 (免调用方拿到被偷改的对象)。"""
    photos = _prod_photos()
    snapshot = copy.deepcopy(photos)
    _heal(photos)
    assert photos == snapshot, "heal_photos 不得改动入参"


def test_heal_keeps_ground_projection_for_non_mirrored_calibrations():
    """反证 (只治垂直): 未被镜像的标定, 其地面投影自愈前后必须逐字节不变。

    417ae 是 render-fix-b1 修好、用户已在生产确认餐桌落位的那一份 —— 必须纹丝不动。
    """
    # 按**顺序**配对, 不可按 photo_id 建索引: 同一 photo id 在 v1/v6/v7 三个 baseline 各有
    # 一份**不同**的标定 (bcc615 的 v1 与 v6/v7 就不同), 按 id 建索引会把三份塌成一份 ->
    # 拿 v1 的结果去比 v7 的存量。生产里每个 baseline 各有自己的 photos.json, 不会碰撞。
    before = _prod_photos()
    healed, report = _heal(_prod_photos())
    assert len(healed) == len(before)
    checked = 0
    for old_p, p in zip(before, healed):
        if p["id"] in _MIRRORED:
            continue
        checked += 1
        old = perspective.Camera.from_dict(old_p["calibration"]["camera"])
        new = perspective.Camera.from_dict(p["calibration"]["camera"])
        x, y, w, h = [v * 10.0 for v in _ROOM_RECTS[p["room_id"]]]
        for fx, fy in ((0.5, 0.5), (0.2, 0.2), (0.8, 0.8)):
            a = np.array(old.project(x + fx * w, y + fy * h, 0.0))
            b = np.array(new.project(x + fx * w, y + fy * h, 0.0))
            assert np.hypot(*(a - b)) < 1e-6, f"{p['id'][:12]}: 地面投影不得移动"
    assert checked == 7, f"应覆盖 7 条未镜像的标定, 实得 {checked}"
    moved = {pid for pid, _rid, _px in calib_heal.summarize(report)["ground_moved"]}
    assert moved == _MIRRORED, f"只有镜像解的地面该移动, 实得 {moved}"


def test_heal_reports_ground_movement_for_mirrored_calibrations():
    """镜像解被纠正 -> 地面移动必须被**如实报出**, 供人工目检定论 (不得静默改)。"""
    _healed, report = _heal(_prod_photos())
    for e in report:
        if e["photo_id"] in _MIRRORED:
            assert e["status"] == "healed"
            assert e["ground_shift_px"] > 1000, (
                f"{e['photo_id'][:12]}: 镜像解的地面位移应被量化报出, 实得 {e['ground_shift_px']}"
            )


def test_heal_skips_payload_without_original_inputs_gracefully():
    """优雅降级: 载荷缺原始输入 -> 提示重新标定, 原样保留, 不得崩。"""
    photos = [
        {"id": "p1", "room_id": "r_live", "calibration": {"camera": {"R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "t": [0, 0, 0], "K": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}}},
    ]
    healed, report = _heal(photos)
    assert healed == photos, "无法重跑的标定必须原样保留"
    assert report[0]["status"] == "skipped_no_inputs"
    assert "重新标定" in report[0]["reason"]


def test_heal_reports_failure_without_aborting_the_batch():
    """单条重算失败不得中断整批, 且该条原样保留。"""
    good = _prod_photos()[0]
    broken = {
        "id": "broken",
        "room_id": "r_live",
        "calibration": {
            "img_wh": [2048, 1536],
            # 同向的两组线 -> 消失点正交约束失败 -> calibrate 抛错
            "x_lines": [[[0, 0], [100, 0]], [[0, 50], [100, 50]]],
            "y_lines": [[[0, 0], [100, 0]], [[0, 50], [100, 50]]],
            "anchors": [{"world": [0, 0, 0], "px": [1, 1]}, {"world": [1000, 0, 0], "px": [50, 1]}],
            "camera": None,
        },
    }
    healed, report = _heal([broken, good])
    assert healed[0] == broken, "重算失败的条目必须原样保留"
    by_id = {e["photo_id"]: e for e in report}
    assert by_id["broken"]["status"] == "failed"
    assert by_id[good["id"]]["status"] == "healed", "同批其余条目仍须照常自愈"


def test_photo_without_calibration_is_passed_through_untouched():
    photos = [{"id": "p0", "room_id": "r_live"}, {"id": "p1", "calibration": {}}]
    healed, report = _heal(photos)
    assert healed == photos
    assert report == [], "未标定的照片不进迁移报告"


def test_healed_calibration_is_not_judged_stale():
    """自愈重写 camera 后不得被判『标定失效』(否则用户被要求无谓地重新标定)。

    binding 指纹只绑 room_id + room_rect_hash, camera 不在其内 (F001 审计 §5.3) —— 本例
    把该结论钉成回归门: 若哪天 binding 把 camera 纳入指纹, 自愈就会连带触发 stale。
    """
    import main

    photos = _prod_photos()
    live = next(p for p in photos if p["room_id"] == "r_live")
    G = {"rooms": [{"id": rid, "rect": rect} for rid, rect in _ROOM_RECTS.items()]}
    live = {**live, "calibration": {**live["calibration"],
                                    "binding": main._calibration_binding(G, "r_live", live)}}
    assert main._calibration_stale_reason(live["calibration"], G, live) is None, "前提: 自愈前不 stale"
    healed, _ = calib_heal.heal_photos([live], room_rects=_ROOM_RECTS)
    assert healed[0]["calibration"]["camera"] != live["calibration"]["camera"], "前提: camera 确被改写"
    assert (
        main._calibration_stale_reason(healed[0]["calibration"], G, healed[0]) is None
    ), "自愈重写 camera 不得被判 stale"


# ---------- fix-round 1 (Evaluator R4): 无法定论的标定须可明确排除 ----------
# 隔离 Evaluator 对 1537e(衣帽间) 的自愈方向目检无法定论 (2 锚点下数据在数学上无法区分
# 两候选; 其锚点 err=195.7px 本就不合格 -> 两候选可能都不对)。用户裁决: 排除, 保持原样,
# 待用户用 >=3 个不共线锚点重标。与其赌一个方向, 不如原样留着。

_CLOAK = "1537e6d839504230972de8a05ee98c8f"


def test_excluded_photo_is_left_untouched_and_reported():
    photos = _prod_photos()
    healed, report = calib_heal.heal_photos(
        photos, room_rects=_ROOM_RECTS, exclude_photo_ids={_CLOAK}
    )
    by_id = {}
    for old_p, new_p in zip(photos, healed):
        if old_p["id"] == _CLOAK:
            assert new_p is old_p or new_p == old_p, "被排除的标定必须原样保留 (逐字节)"
        by_id.setdefault(old_p["id"], []).append((old_p, new_p))
    excluded = [e for e in report if e["photo_id"] == _CLOAK]
    assert len(excluded) == 2, "1537e 在 v6/v7 各一条, 应各报一次"
    for e in excluded:
        assert e["status"] == "excluded"
        assert "重新标定" in e["reason"], "须说明为何排除 (不得静默跳过)"


def test_exclusion_does_not_affect_other_calibrations():
    """排除 1537e 不得连累其余 9 条 —— 尤其 dabcb (已获目检确认) 仍须自愈。"""
    _healed, report = calib_heal.heal_photos(
        _prod_photos(), room_rects=_ROOM_RECTS, exclude_photo_ids={_CLOAK}
    )
    counts = calib_heal.summarize(report)["counts"]
    assert counts.get("healed") == 9, f"其余 9 条仍须自愈, 实得 {counts}"
    assert counts.get("excluded") == 2
    healed_ids = {e["photo_id"] for e in report if e["status"] == "healed"}
    assert "dabcb951390546d8a118a90e02940e30" in healed_ids, "dabcb 已获目检确认, 必须自愈"


def test_excluded_calibration_stays_physically_invalid_and_is_not_hidden():
    """诚实边界: 被排除的条目仍是未修复状态, 报告不得让它看起来已解决。"""
    _healed, report = calib_heal.heal_photos(
        _prod_photos(), room_rects=_ROOM_RECTS, exclude_photo_ids={_CLOAK}
    )
    s = calib_heal.summarize(report)
    assert s["counts"].get("excluded") == 2
    # 被排除的条目不参与 new_camera_z 统计 -> 不得被计入"已修好"
    for e in report:
        if e["status"] == "excluded":
            assert e["new_camera_z"] is None, "排除项不得报出新值 (它没被重算)"
