# -*- coding: utf-8 -*-
"""特征点标定 (calib-cure-b1 F008, spec §4.2 路线一): 特征点池派生 + 共面 PnP 求解。

范式转变: 专家模式要求用户生产『抽象对应关系』(罗盘角标 + 方向线分组), 极易错且 2 锚点
不可检 (缺陷核查 20260717 实验二 case A: 角标互换自报误差 0.0px)。特征点模式反过来 ——
**点从模型上拿, 自带世界坐标**, 用户只做"在照片上点它在哪"这一件视觉任务; ≥4 点天然冗余,
粗差直接表现为大残差, 被 assess 硬门当场拦下。

特征点池 (全部 z=0 地面点, 不依赖开口高度数据):
  - 实体墙角: merge 组成员 rect 四角, 跨成员重复坐标 = 开放边界上的虚拟角, 剔除
    (f4d 病灶: 门厅与客厅开放边界的"墙角"现实中无实体特征);
  - 门框竖边×地面交点: openings 门每樘 2 点 (wall{axis,at,span} 毫米级平面定位);
  - 落地窗框×地面交点: kind=window 且 wtype=='full' (实证: r_master 南窗 wtype=full =
    落地窗, 见 BL-decor-b2-test-fixture-harden 记录); normal/high 窗台高度无数据, 不出点。

solve_pnp: 共面点单应 (Hartley 归一化 DLT) -> 焦距扫描 (HFOV 40-110°) 逐档分解
[r1 r2 t] -> SVD 极分解正交化 -> 物理门 (相机在地上/点在相机前) -> 取最小重投影残差档
-> 邻域细扫。世界系与 perspective 同约定 (X=东, Y=南, Z=上, 左手系, R 的 z 列 =
-cross(x,y), det=-1); 相机在地上的过滤唯一确定 r3 符号与 t 符号。纯 numpy, 确定性。
"""

from __future__ import annotations

import numpy as np
from floorplan_core import axon

from . import perspective

# 焦距扫描范围与密度: 手机镜头合理水平视场 (与 assess 的 HFOV_RANGE_DEG 同源);
# 粗扫 41 档后在最优档 ±2° 细扫 21 档, 合成真值往返 <2px (单测钉住)。
_HFOV_SCAN_DEG = (40.0, 110.0, 41)
_HFOV_REFINE_HALF_DEG = 2.0
_HFOV_REFINE_STEPS = 21

_CORNER_NAMES = ("西北", "东北", "东南", "西南")


def derive_features(G: dict, room_id: str) -> tuple[list[dict], list[str]]:
    """标定特征点池 -> (features, merge 成员 id 列表)。

    features: [{id, world:[x_mm,y_mm,0], label_zh, kind}], id 稳定可复算 (binding/UI 引用)。
    kind: wall_corner | door_jamb | window_floor。房间不存在时退回单成员 (同 render 侧容错)。
    """
    rooms_by_id = {str(r["id"]): r for r in G.get("rooms", []) if "id" in r}
    try:
        members = sorted(str(m) for m in axon.merge_group_ids(G, str(room_id)))
    except Exception:  # noqa: BLE001 - 房间已删/无 merge: 退回本房
        members = [str(room_id)]
    mm = float((G.get("meta", {}) or {}).get("mm_per_px", 10))
    feats: list[dict] = []

    # 1) 实体墙角: 跨成员重复坐标 = 开放边界虚拟角, 双方剔除。
    seen: dict = {}
    for mid in members:
        room = rooms_by_id.get(mid)
        if room is None:
            continue
        x, y, w, h = room["rect"]
        label = ((room.get("label") or {}).get("zh")) or mid
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        for cname, (cx, cy) in zip(_CORNER_NAMES, corners):
            key = (round(float(cx), 1), round(float(cy), 1))
            seen.setdefault(key, []).append(
                {
                    "id": f"corner:{mid}:{cname}",
                    "world": [float(cx) * mm, float(cy) * mm, 0.0],
                    "label_zh": f"{label}·{cname}角",
                    "kind": "wall_corner",
                }
            )
    for lst in seen.values():
        if len(lst) == 1:
            feats.append(lst[0])

    # 2) 开口框边×地面交点: 门全收; 窗仅落地 (wtype=='full')。开口须贴任一成员 rect 边界。
    eps = 1.0

    def _on_boundary(px_: float, py_: float) -> bool:
        for mid in members:
            room = rooms_by_id.get(mid)
            if room is None:
                continue
            x, y, w, h = room["rect"]
            on_v = (abs(px_ - x) <= eps or abs(px_ - (x + w)) <= eps) and (
                y - eps <= py_ <= y + h + eps
            )
            on_h = (abs(py_ - y) <= eps or abs(py_ - (y + h)) <= eps) and (
                x - eps <= px_ <= x + w + eps
            )
            if on_v or on_h:
                return True
        return False

    for op in G.get("openings", []) or []:
        kind = op.get("kind")
        if kind == "door":
            zh, fkind = "门框", "door_jamb"
        elif kind == "window" and op.get("wtype") == "full":
            zh, fkind = "落地窗框", "window_floor"
        else:
            continue
        wall = op.get("wall") or {}
        axis, at, span = wall.get("axis"), wall.get("at"), wall.get("span")
        if axis not in ("h", "v") or at is None or not span or len(span) != 2:
            continue
        jambs = (
            [(at, span[0]), (at, span[1])] if axis == "v" else [(span[0], at), (span[1], at)]
        )
        oid = op.get("id") or f"{axis}{at}"
        for suffix, (jx, jy) in zip(("a", "b"), jambs):
            if not _on_boundary(float(jx), float(jy)):
                continue
            feats.append(
                {
                    "id": f"{kind}:{oid}:{suffix}",
                    "world": [float(jx) * mm, float(jy) * mm, 0.0],
                    "label_zh": f"{zh} {oid}·地面交点{suffix}",
                    "kind": fkind,
                }
            )
    feats.sort(key=lambda f_: f_["id"])
    return feats, members


# ---- 共面 PnP (单应分解 + 焦距扫描) ------------------------------------------------


def _normalise(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley 归一化: 质心平移 + 平均距离缩放到 √2 (DLT 条件数)。"""
    c = pts.mean(axis=0)
    d = float(np.sqrt(((pts - c) ** 2).sum(axis=1)).mean())
    s = (2.0**0.5) / (d or 1.0)
    T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1.0]])
    return T, (pts - c) * s


def _homography(world_xy: np.ndarray, px: np.ndarray) -> np.ndarray:
    Tw, wn = _normalise(world_xy)
    Tp, pn = _normalise(px)
    rows = []
    for (X, Y), (u, v) in zip(wn, pn):
        rows.append([-X, -Y, -1.0, 0, 0, 0, u * X, u * Y, u])
        rows.append([0, 0, 0, -X, -Y, -1.0, v * X, v * Y, v])
    _, _, Vt = np.linalg.svd(np.asarray(rows, float))
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Tp) @ Hn @ Tw
    if abs(H[2, 2]) < 1e-12:
        raise ValueError("单应退化 (特征点可能共线或重复)")
    return H / H[2, 2]


def _pose_candidates(H: np.ndarray, K: np.ndarray):
    """K⁻¹H = [r1' r2' t'] -> 两个符号候选, SVD 极分解取最近正交列对; r3 = -cross (左手系)。"""
    M = np.linalg.inv(K) @ H
    for s in (1.0, -1.0):
        r1, r2, t = s * M[:, 0], s * M[:, 1], s * M[:, 2]
        n1, n2 = np.linalg.norm(r1), np.linalg.norm(r2)
        if n1 < 1e-12 or n2 < 1e-12:
            continue
        lam = 2.0 / (n1 + n2)
        A = np.column_stack([r1 * lam, r2 * lam])
        U, _sv, Vt = np.linalg.svd(A, full_matrices=False)
        B = U @ Vt
        R = np.column_stack([B[:, 0], B[:, 1], -np.cross(B[:, 0], B[:, 1])])
        yield R, t * lam


def solve_pnp(points: list, *, img_wh: tuple) -> "perspective.Camera":
    """≥4 个共面 (z=0) 特征点对 [((x,y,0),(u,v)), ...] -> Camera。

    焦距扫描逐档分解评分 (评分 = 正交化后姿态的最大重投影残差, 对错误焦距敏感), 物理门
    (相机在地上 + 点在相机前) 过滤符号歧义。合成真值往返 <2px (单测钉住); 粗差输入表现为
    大残差, 由上层 assess 硬门拦截 —— 本函数只拒绝完全无解的退化输入。
    """
    if len(points) < 4:
        raise ValueError("solve_pnp 需 ≥4 个特征点")
    for w, _p in points:
        if abs(float(w[2])) > 1e-6:
            raise ValueError("特征点须为地面点 (z=0)")
    world = np.array([[float(w[0]), float(w[1])] for w, _p in points], float)
    px = np.array([[float(p[0]), float(p[1])] for _w, p in points], float)
    W, H_img = float(img_wh[0]), float(img_wh[1])
    cx, cy = W / 2.0, H_img / 2.0
    Hm = _homography(world, px)

    def _score(hfovs):
        best = None
        for hfov in hfovs:
            f = (W / 2.0) / np.tan(np.radians(hfov) / 2.0)
            K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
            for R, t in _pose_candidates(Hm, K):
                if float((-R.T @ t)[2]) <= 0:  # 相机必须在地板上方
                    continue
                cam_pts = R @ np.vstack([world.T, np.zeros(len(points))]) + t.reshape(3, 1)
                depth = cam_pts[2]
                if np.any(depth <= 1e-6):  # 点必须在相机前方
                    continue
                uv = K @ cam_pts
                proj = (uv[:2] / depth).T
                err = float(np.max(np.hypot(*(proj - px).T)))
                if best is None or err < best[0]:
                    best = (err, hfov, K, R, t)
        return best

    lo, hi, n = _HFOV_SCAN_DEG
    best = _score(np.linspace(lo, hi, int(n)))
    if best is None:
        raise ValueError("无物理有效的相机姿态解 (特征点世界/像素对应可能有误)")
    # 两级细扫收敛到 ~0.025° 粒度 (残差随焦距误差近似线性, 0.2° 粒度实测残 ~3px 不达标)。
    for half in (_HFOV_REFINE_HALF_DEG, 0.3):
        refine = _score(
            np.linspace(
                max(lo, best[1] - half), min(hi, best[1] + half), _HFOV_REFINE_STEPS + 4
            )
        )
        if refine is not None and refine[0] < best[0]:
            best = refine
    _err, _hfov, K, R, t = best
    return perspective.Camera(K=K, R=R, t=np.asarray(t, float))
