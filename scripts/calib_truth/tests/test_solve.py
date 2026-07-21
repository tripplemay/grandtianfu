"""calib-route-a1 F001 — solve.py 的合成数据验证。

跑法（本批研究码不在 api 的 PYTHONPATH 里）：
    python3 -m pytest scripts/calib_truth/tests -q
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solve as S  # noqa: E402


CEIL = 2700.0


def make_camera(f=900.0, cx=1024.0, cy=768.0,
                cam_xyz=(3000.0, -4000.0, 1500.0), look_at=(3000.0, 1950.0, 1200.0)):
    """构造一台**左手世界系**（X东/Y南/Z上，mm）下物理有效的相机。

    按相机自身的正交基构造，而**不是**按世界轴构造 —— R 的行 = 相机的
    (right, down, forward) 在世界系中的方向，故 X_cam = R @ X_world + t。

    ⚠ 世界坐标元组 (X东, Y南, Z上) 相对物理空间是**左手**的（物理上 东×南 = 下），
    而相机基 (right, down, forward) 是物理右手的 —— 两者之间的基变换矩阵因此
    必然 **det(R) = -1**。本函数以断言把这条钉住：它不是可调的符号约定，
    是几何事实。写成 det=+1 即 calib-z-b1 的「相机解到地板下方」。
    """
    C = np.array(cam_xyz, float)
    fwd = np.array(look_at, float) - C
    fwd /= np.linalg.norm(fwd)
    up = np.array([0.0, 0.0, 1.0])                 # 世界的「上」
    down = -(up - np.dot(up, fwd) * fwd)           # 与视线正交的「下」
    down /= np.linalg.norm(down)
    right = np.cross(down, fwd)                    # 数值叉积
    R = np.vstack([right, down, fwd])
    if np.linalg.det(R) > 0:                       # 左手世界系下须为负
        right = -right
        R = np.vstack([right, down, fwd])
    assert np.linalg.det(R) < 0, "左手世界系 x 右手相机基 => det(R) 必为负"
    t = -R @ C
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    return K, R, t


def room_points(x0=0.0, y0=0.0, w=6000.0, h=3900.0):
    """一个房间的 8 个角（地面 4 + 天花 4）—— 天然非共面。"""
    fl = [(x0, y0, 0.0), (x0 + w, y0, 0.0), (x0 + w, y0 + h, 0.0), (x0, y0 + h, 0.0)]
    return fl + [(x, y, CEIL) for x, y, _ in fl]


def synth(K, R, t, pts, noise_px=0.0, seed=0):
    W = np.array(pts, float)
    uv = S.project(K, R, t, W)
    if noise_px:
        uv = uv + np.random.default_rng(seed).normal(0, noise_px, uv.shape)
    return [(tuple(w), tuple(p)) for w, p in zip(W, uv)]


# ------------------------------------------------------------------ 基本反解

def test_noiseless_recovers_camera_exactly():
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points() + [(1500.0, 900.0, 2050.0), (4500.0, 900.0, 2050.0)])
    K2, R2, t2 = S.solve_camera(corr)
    assert S.reproj_errors(K2, R2, t2, corr).max() < 1e-3
    assert abs(K2[0, 0] - K[0, 0]) / K[0, 0] < 1e-4
    assert np.allclose(R2, R, atol=1e-5)
    assert np.allclose(t2, t, rtol=1e-4, atol=1e-2)


def test_preserves_left_handed_determinant():
    """det(R) 必须保持为负 —— 强制 SO(3) 正是 calib-z-b1 的根因。"""
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points())
    K2, R2, t2 = S.solve_camera(corr)
    assert np.linalg.det(R2) < 0
    # 相机中心须在地板上方（该约束地面点给不了，此处非共面点能给）
    assert float((-R2.T @ t2)[2]) > 0


def test_refine_keeps_determinant_sign_over_iterations():
    """refine 用 R0 @ expm(so3) 参数化，expm 恒 det=+1，故符号被保住。"""
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points(), noise_px=2.0, seed=3)
    Kd, Rd, td = S.enforce_cheirality(*S.decompose(S.dlt(corr)), corr)
    assert np.linalg.det(Rd) < 0, "消歧后应落在物理正确（左手）分支"
    K2, R2, t2 = S.refine(Kd, Rd, td, corr)
    assert np.linalg.det(R2) < 0


def test_cheirality_is_what_picks_the_handedness():
    """det 符号由「点在相机前方」自动定下，不是被硬拗的。

    直接取 DLT 分解结果（未消歧）时，符号可能落在错误分支且深度为负；
    enforce_cheirality 一步同时修好深度与手性 —— 二者本就是同一件事。
    """
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points())
    W = np.array([c[0] for c in corr], float)
    Kd, Rd, td = S.decompose(S.dlt(corr))
    Kc, Rc, tc = S.enforce_cheirality(Kd, Rd, td, corr)
    assert (W @ Rc.T + tc)[:, 2].min() > 0, "消歧后所有点须在相机前方"
    assert np.linalg.det(Rc) < 0
    if np.linalg.det(Rd) > 0:                      # 确实发生了翻转
        assert (W @ Rd.T + td)[:, 2].max() < 0, "错误分支应表现为点全在背后"


# ------------------------------------------------------------------ 退化拒解

def test_coplanar_points_are_rejected_not_silently_wrong():
    """全共面 -> 必须**明确报错**。b2/b3 死在这类位形被静默接受。"""
    K, R, t = make_camera()
    coplanar = [(x, y, 0.0) for x, y, _ in room_points()] + [(3000.0, 1000.0, 0.0)]
    corr = synth(K, R, t, coplanar)
    with pytest.raises(ValueError, match="共面"):
        S.solve_camera(corr)


def test_too_few_points_rejected():
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points()[:5])
    with pytest.raises(ValueError, match=">=6"):
        S.solve_camera(corr)


# ------------------------------------------------------------------ 留一法

def test_leave_one_out_uncertainty_tracks_noise():
    """留出误差应随标注噪声单调上升 —— 它才是真值不确定度的度量。"""
    K, R, t = make_camera()
    pts = room_points() + [(1500.0, 900.0, 2050.0), (4500.0, 900.0, 2050.0),
                           (0.0, 1950.0, 1350.0), (6000.0, 1950.0, 1350.0)]
    out = []
    for noise in (0.0, 1.0, 3.0):
        corr = synth(K, R, t, pts, noise_px=noise, seed=11)
        out.append(S.leave_one_out(corr)["median_px"])
    assert out[0] < 0.05, f"无噪声时留出误差应近零, 实得 {out[0]}"
    assert out[0] < out[1] < out[2], f"留出误差未随噪声上升: {out}"


def test_leave_one_out_needs_seven_points():
    K, R, t = make_camera()
    corr = synth(K, R, t, room_points()[:6])
    with pytest.raises(ValueError, match=">=7"):
        S.leave_one_out(corr)


def test_leave_one_out_reports_every_holdout():
    K, R, t = make_camera()
    pts = room_points() + [(1500.0, 900.0, 2050.0)]
    corr = synth(K, R, t, pts, noise_px=1.0, seed=5)
    r = S.leave_one_out(corr)
    assert r["n"] == len(corr)
    assert len(r["holdout_px"]) == r["n_evaluated"]
    assert r["max_px"] >= r["median_px"]


def test_holdout_error_exceeds_fit_error_under_noise():
    """留出误差 > 拟合误差 —— 若反过来说明在自欺（拟合精度当成了泛化精度）。"""
    K, R, t = make_camera()
    pts = room_points() + [(1500.0, 900.0, 2050.0), (4500.0, 900.0, 2050.0)]
    corr = synth(K, R, t, pts, noise_px=2.0, seed=7)
    K2, R2, t2 = S.solve_camera(corr)
    fit = float(np.median(S.reproj_errors(K2, R2, t2, corr)))
    held = S.leave_one_out(corr)["median_px"]
    assert held > fit
