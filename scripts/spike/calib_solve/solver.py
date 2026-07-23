# -*- coding: utf-8 -*-
"""calib-cure-b2 F001 spike — 候选解算器原型 (纯 numpy, 隔离研究码)。

范式对比:
- 现产品 `calib_features.solve_pnp`: 共面单应分解 (要求全部点 z=0)，真实斜拍照可见地面点
  又少又近共线 → 退化 (spec §1: r_study 4点共线比≈0 → 100% 失败)。
- 本原型 `solve_pnp_general`: 接受**异面点** (z 任意), 焦距扫描 + 已知K位姿归一化DLT +
  正交化 + 物理门 + 最小重投影档 → **非线性精修 (Gauss-Newton, 全点最小化总重投影)**。
  异面点 (地面 + 天花板 z=2700 + 竖直棱) 破共面退化, 精修把点击噪声平均掉。

世界系与 perspective 同约定: X=东, Y=南, Z=上, 左手系 (物理真实相机 det(R)=-1)。
不 import main.py; 只读复用 aigc.perspective.Camera (纯几何, 运行时 PYTHONPATH 提供)。
"""

from __future__ import annotations

import numpy as np

# 焦距扫描 (与 assess HFOV_RANGE_DEG 同源手机镜头范围); 精修后对焦距不敏感, 粗扫足够。
_HFOV_SCAN_DEG = (35.0, 115.0, 33)


def _K(f: float, cx: float, cy: float) -> np.ndarray:
    return np.array([[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]])


def _solve_pose_known_K(world: np.ndarray, px: np.ndarray, K: np.ndarray):
    """已知 K, 从 ≥6 (或 ≥4 异面) 3D-2D 对解 [R|t] (归一化 DLT + 正交化)。

    产出两个符号候选 (DLT 零空间的整体符号歧义), 由物理门在调用处筛。
    左手世界: 物理解 det(R)=-1; 正交化用 SVD 取最近正交阵, 不强加 det 号 (让数据定)。
    """
    Kinv = np.linalg.inv(K)
    n = len(world)
    Xh = np.c_[world, np.ones(n)]            # n×4 齐次世界点
    xn = (Kinv @ np.c_[px, np.ones(n)].T).T  # n×3 归一化像点 (bearing)
    rows = []
    for i in range(n):
        x, y, w = xn[i]
        X = Xh[i]
        rows.append(np.concatenate([np.zeros(4), -w * X, y * X]))
        rows.append(np.concatenate([w * X, np.zeros(4), -x * X]))
    _, _, Vt = np.linalg.svd(np.asarray(rows, float))
    M = Vt[-1].reshape(3, 4)
    for s in (1.0, -1.0):
        Ms = s * M
        R_raw, t_raw = Ms[:, :3], Ms[:, 3]
        U, S, Vt2 = np.linalg.svd(R_raw)
        if S.mean() < 1e-12:
            continue
        R = U @ Vt2                    # 最近正交阵
        scale = 1.0 / S.mean()         # R_raw ≈ scale·R
        t = t_raw * scale
        yield R, t


def _project(f, R, t, cx, cy, world):
    """(f,R,t) 投影世界点 -> 像素 (n×2) + 深度 (n,)。"""
    cam = R @ world.T + t.reshape(3, 1)          # 3×n
    depth = cam[2]
    u = f * cam[0] / depth + cx
    v = f * cam[1] / depth + cy
    return np.column_stack([u, v]), depth


def _reproj_errs(f, R, t, cx, cy, world, px):
    proj, depth = _project(f, R, t, cx, cy, world)
    return np.hypot(*(proj - px).T), depth


def _rodrigues(rvec: np.ndarray) -> np.ndarray:
    """旋转向量 -> 旋转矩阵 (det=+1)。左手解用 base_R 承载手性, rvec 只表增量。"""
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * Kx + (1 - np.cos(theta)) * (Kx @ Kx)


def _refine_gauss_newton(f0, R0, t0, cx, cy, world, px, iters=30):
    """非线性精修: 对 (f, 旋转增量 rvec, t) 最小化总重投影 (Gauss-Newton + LM 阻尼)。

    参数 7 维 [dlog_f, rx, ry, rz, tx, ty, tz]; R = R0·Rodrigues(rvec) 保持 det(R0) 手性。
    数值雅可比 (纯 numpy, 无 scipy); LM 阻尼保稳。返回 (f, R, t)。
    """
    p = np.zeros(7)
    base_f, base_R, base_t = f0, R0.copy(), t0.copy()

    def residual(p):
        if abs(p[0]) > 2.0:            # 焦距增量钳制 (exp(2)≈7.4×), 防退化初值下 log_f 爆
            return None
        f = base_f * np.exp(p[0])
        R = base_R @ _rodrigues(p[1:4])
        t = base_t + p[4:7]
        proj, depth = _project(f, R, t, cx, cy, world)
        if np.any(depth <= 1e-6) or not np.all(np.isfinite(proj)):
            return None
        return (proj - px).reshape(-1)

    r = residual(p)
    if r is None:
        return f0, R0, t0
    lam = 1e-3
    cost = float(r @ r)
    for _ in range(iters):
        # 数值雅可比
        J = np.zeros((len(r), 7))
        eps = 1e-6
        ok = True
        for j in range(7):
            dp = p.copy()
            dp[j] += eps
            rj = residual(dp)
            if rj is None:
                ok = False
                break
            J[:, j] = (rj - r) / eps
        if not ok:
            break
        H = J.T @ J
        g = J.T @ r
        for _ls in range(8):  # LM 阻尼线搜索
            try:
                step = np.linalg.solve(H + lam * np.eye(7), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            r_new = residual(p + step)
            if r_new is not None and float(r_new @ r_new) < cost:
                p = p + step
                r = r_new
                cost = float(r @ r)
                lam = max(lam * 0.5, 1e-9)
                break
            lam *= 10
        else:
            break
    f = base_f * np.exp(p[0])
    R = base_R @ _rodrigues(p[1:4])
    t = base_t + p[4:7]
    return f, R, t


def solve_pnp_general(points, *, img_wh, refine=True):
    """≥4 个 3D-2D 特征点对 [((x,y,z),(u,v)), ...] (可异面) -> perspective.Camera。

    异面点 (地面+天花板+竖直) 使位姿良态; 焦距扫描定初值, Gauss-Newton 精修降噪。
    只拒绝完全无物理解的退化输入 (粗差由上层 assess 硬门拦)。
    """
    from aigc import perspective

    if len(points) < 4:
        raise ValueError("solve_pnp_general 需 ≥4 个特征点")
    world = np.array([[float(w[0]), float(w[1]), float(w[2])] for w, _p in points], float)
    px = np.array([[float(p[0]), float(p[1])] for _w, p in points], float)
    W, Hh = float(img_wh[0]), float(img_wh[1])
    cx, cy = W / 2.0, Hh / 2.0

    lo, hi, n = _HFOV_SCAN_DEG
    best = None
    for hfov in np.linspace(lo, hi, int(n)):
        f = (W / 2.0) / np.tan(np.radians(hfov) / 2.0)
        K = _K(f, cx, cy)
        for R, t in _solve_pose_known_K(world, px, K):
            C = -R.T @ t
            if C[2] <= 0:                       # 相机须在地板上方
                continue
            errs, depth = _reproj_errs(f, R, t, cx, cy, world, px)
            if np.any(depth <= 1e-6):           # 点须在相机前方
                continue
            score = float(np.max(errs))
            if best is None or score < best[0]:
                best = (score, f, R, t)
    if best is None:
        raise ValueError("无物理有效的相机姿态解 (特征点世界/像素对应可能有误)")
    _, f, R, t = best
    if refine:
        f, R, t = _refine_gauss_newton(f, R, t, cx, cy, world, px)
    K = _K(f, cx, cy)
    return perspective.Camera(K=K, R=R, t=np.asarray(t, float))


def degeneracy(points) -> dict:
    """点位退化度量 (spec §D3 守门依据)。

    - collinear_ratio: 地面点 XY 分布奇异值比 s_min/s_max (→0 近共线, 共面 PnP 死局);
    - height_span_mm: 点 Z 跨度 (=0 表全共面地面点, 通用 PnP 无异面约束);
    - n_points: 有效点数。
    低 collinear_ratio 且 height_span=0 = 现产品失败的典型输入。
    """
    W = np.array([[float(w[0]), float(w[1]), float(w[2])] for w, _p in points], float)
    xy = W[:, :2] - W[:, :2].mean(0)
    s = np.linalg.svd(xy, compute_uv=False)
    ratio = float(s[-1] / s[0]) if s[0] > 1e-9 else 0.0
    return {
        "n_points": len(points),
        "collinear_ratio": round(ratio, 4),
        "height_span_mm": round(float(np.ptp(W[:, 2])), 1),
    }
