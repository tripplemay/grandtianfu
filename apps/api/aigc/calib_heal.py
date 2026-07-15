# -*- coding: utf-8 -*-
"""存量标定自愈 (calib-z-b1 F002): 用修好的 calibrate() 重跑存量原始输入 -> 导出正确 camera。

存储载荷 photo.calibration 完整保留了标定的原始输入 (x_lines / y_lines / anchors / img_wh),
故 F001 修好符号后**重跑即可**, 无需用户重新标定 (spec §D3)。

本模块是**纯函数, 无任何文件 I/O 且不改入参** —— 落盘由 scripts/migrate_calibration_z.py
负责 (仓库惯例: 逻辑在模块可测, scripts/ 只作薄 CLI, 见 scripts/migrate_scheme_status.py)。
这样也避免把 numpy 拖进纯 stdlib 的 baselines.py 存储层。
"""

from __future__ import annotations

import numpy as np

from . import perspective

# 地面位移探针取房间 rect 内的相对位置。**不得用锚点自身当探针** —— 修前的两个候选对
# 锚点的重投影完全等价 (精确平局正是这么来的), 用锚点探测恒得 ~0 位移, 会把镜像解误报
# 成"没变" (testing-env-patterns §7 退化位置 fixture)。
_PROBE_FRACS = ((0.5, 0.5), (0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8))

# 判定"无需改写"的容差 (R/t 各分量)。跨机器 BLAS 末位差异不应触发无谓改写。
_SAME_CAMERA_ATOL = 1e-9


def _has_original_inputs(cal: dict) -> bool:
    if not isinstance(cal, dict):
        return False
    if not all(cal.get(k) for k in ("x_lines", "y_lines", "anchors")):
        return False
    wh = cal.get("img_wh")
    return isinstance(wh, (list, tuple)) and len(wh) == 2


def _to_line(ln):
    return (tuple(ln[0]), tuple(ln[1]))


def _recalibrate(cal: dict) -> perspective.Camera:
    return perspective.calibrate(
        [_to_line(ln) for ln in cal["x_lines"]],
        [_to_line(ln) for ln in cal["y_lines"]],
        [(tuple(a["world"]), tuple(a["px"])) for a in cal["anchors"]],
        img_wh=tuple(cal["img_wh"]),
    )


def camera_height_mm(cam_dict: dict) -> float:
    """相机中心的世界 z (mm): C = -R^T t 的 z 分量。<=0 = 解在地板下方 = 物理不可能。"""
    R = np.array(cam_dict["R"], float)
    t = np.array(cam_dict["t"], float)
    return float((-R.T @ t)[2])


def _same_camera(a: dict | None, b: dict) -> bool:
    if not isinstance(a, dict) or "R" not in a or "t" not in a:
        return False
    try:
        return bool(
            np.allclose(np.array(a["R"], float), np.array(b["R"], float), atol=_SAME_CAMERA_ATOL)
            and np.allclose(np.array(a["t"], float), np.array(b["t"], float), atol=_SAME_CAMERA_ATOL)
        )
    except Exception:  # noqa: BLE001 - 载荷畸形一律当"不同", 交由重算覆盖
        return False


def _ground_shift_px(old: dict, new: dict, rect, mm_per_px: float) -> float | None:
    """房间 rect 内若干地面点在新旧相机下的最大投影位移 (px)。rect 缺失 -> None。"""
    if not rect or len(rect) != 4:
        return None
    try:
        cam_old = perspective.Camera.from_dict(old)
        cam_new = perspective.Camera.from_dict(new)
    except Exception:  # noqa: BLE001
        return None
    x, y, w, h = [float(v) * mm_per_px for v in rect]
    worst = 0.0
    for fx, fy in _PROBE_FRACS:
        gx, gy = x + fx * w, y + fy * h
        a = np.array(cam_old.project(gx, gy, 0.0))
        b = np.array(cam_new.project(gx, gy, 0.0))
        worst = max(worst, float(np.hypot(*(a - b))))
    return worst


def heal_photos(
    photos: list[dict],
    *,
    room_rects: dict | None = None,
    mm_per_px: float = 10.0,
) -> tuple[list[dict], list[dict]]:
    """重跑每条标定的原始输入 -> (新 photos 列表, 逐条报告)。

    纯函数: 不改 ``photos``, 未变更的条目原样透传 (同一对象), 变更的条目返回新 dict。
    幂等: 对已自愈的数据再跑一次, 重算结果与存量一致 -> 全部 status="unchanged", 零改写。

    report 每条: {photo_id, room_id, status, stored_camera_z, new_camera_z, ground_shift_px, reason}
    status: healed(已重算并改写) / unchanged(重算与存量一致) /
            skipped_no_inputs(载荷缺原始输入, 需用户重新标定) / failed(重算报错, 原样保留)
    """
    room_rects = room_rects or {}
    out: list[dict] = []
    report: list[dict] = []
    for ph in photos:
        cal = ph.get("calibration") if isinstance(ph, dict) else None
        entry = {
            "photo_id": (ph or {}).get("id"),
            "room_id": (ph or {}).get("room_id"),
            "status": None,
            "stored_camera_z": None,
            "new_camera_z": None,
            "ground_shift_px": None,
            "reason": None,
        }
        if not isinstance(cal, dict) or not cal:
            out.append(ph)
            continue  # 未标定的照片不进报告 (不是本次迁移的对象)
        if not _has_original_inputs(cal):
            # 优雅降级: 缺原始输入 -> 无法重跑, 原样保留并提示重新标定 (不得崩)
            out.append(ph)
            entry.update(status="skipped_no_inputs", reason="标定载荷缺原始输入 (x_lines/y_lines/anchors/img_wh), 需用户重新标定")
            report.append(entry)
            continue
        stored = cal.get("camera")
        if isinstance(stored, dict) and "R" in stored:
            try:
                entry["stored_camera_z"] = round(camera_height_mm(stored), 1)
            except Exception:  # noqa: BLE001
                pass
        try:
            cam = _recalibrate(cal)
        except Exception as exc:  # noqa: BLE001 - 单条重算失败不得中断整批
            out.append(ph)
            entry.update(status="failed", reason=f"重算失败: {exc}")
            report.append(entry)
            continue
        new_cam = cam.to_dict()
        entry["new_camera_z"] = round(camera_height_mm(new_cam), 1)
        if _same_camera(stored, new_cam):
            out.append(ph)
            entry.update(status="unchanged")
            report.append(entry)
            continue
        if isinstance(stored, dict):
            entry["ground_shift_px"] = _ground_shift_px(
                stored, new_cam, room_rects.get(ph.get("room_id")), mm_per_px
            )
        out.append({**ph, "calibration": {**cal, "camera": new_cam}})
        entry.update(status="healed")
        report.append(entry)
    return out, report


def summarize(report: list[dict]) -> dict:
    """报告计数 (供 CLI 与核对报告)。"""
    counts: dict = {}
    for e in report:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {
        "total": len(report),
        "counts": counts,
        "camera_below_floor_before": sum(
            1 for e in report if isinstance(e["stored_camera_z"], (int, float)) and e["stored_camera_z"] <= 0
        ),
        "camera_below_floor_after": sum(
            1 for e in report if isinstance(e["new_camera_z"], (int, float)) and e["new_camera_z"] <= 0
        ),
        "ground_moved": sorted(
            (e["photo_id"], e["room_id"], round(e["ground_shift_px"], 1))
            for e in report
            if isinstance(e.get("ground_shift_px"), (int, float)) and e["ground_shift_px"] > 1.0
        ),
    }
