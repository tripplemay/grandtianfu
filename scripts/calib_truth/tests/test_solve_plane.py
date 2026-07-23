"""calib-route-a1 F001 — 单平面（地面）标定验证。

核心断言不是「能解」，而是**退化边界的位置**：地面永远可解，正对的墙永远不可解。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solve as S            # noqa: E402
import solve_plane as SP     # noqa: E402
from test_solve import make_camera, synth  # noqa: E402

WH = (2048, 1536)
F = 821.0
# 一间 6.0 x 3.9m 的房，地面 4 角 + 2 个门框底（门洞下沿也在地面上）
FLOOR = [(12150.0, 10200.0, 0.0), (18150.0, 10200.0, 0.0),
         (18150.0, 14100.0, 0.0), (12150.0, 14100.0, 0.0),
         (14300.0, 10200.0, 0.0), (15150.0, 10200.0, 0.0)]


def cam(**kw):
    kw.setdefault("f", F)
    kw.setdefault("cx", WH[0] / 2)
    kw.setdefault("cy", WH[1] / 2)
    kw.setdefault("cam_xyz", (17000.0, 15500.0, 1500.0))
    kw.setdefault("look_at", (14000.0, 11000.0, 1200.0))
    return make_camera(**kw)


# ------------------------------------------------------------------ 精度

def test_five_floor_points_recover_focal():
    """5 个是下限：单应只要 4 个，但 4 个无从做留一自检 -> 不允许。"""
    K, R, t = cam()
    K2, _, _, info = SP.solve_camera_plane(synth(K, R, t, FLOOR[:5]), WH)
    assert abs(K2[0, 0] - F) / F < 0.01
    assert info["n_stable"] >= 1


def test_four_points_rejected_because_self_check_impossible():
    K, R, t = cam()
    with pytest.raises(ValueError, match=">=5"):
        SP.solve_camera_plane(synth(K, R, t, FLOOR[:4]), WH)


@pytest.mark.parametrize("noise,limit", [(0.0, 0.002), (1.0, 0.02), (3.0, 0.05)])
def test_focal_accuracy_degrades_gracefully_with_noise(noise, limit):
    K, R, t = cam()
    corr = synth(K, R, t, FLOOR, noise_px=noise, seed=4)
    K2, _, _, _ = SP.solve_camera_plane(corr, WH)
    assert abs(K2[0, 0] - F) / F < limit


def test_recovers_pose_and_camera_height():
    K, R, t = cam()
    K2, R2, t2, _ = SP.solve_camera_plane(synth(K, R, t, FLOOR, noise_px=0.5, seed=1), WH)
    C = -R2.T @ t2
    assert abs(C[2] - 1500.0) < 120.0, f"相机高应 ~1500mm, 实得 {C[2]:.0f}"
    assert np.linalg.norm(C[:2] - np.array([17000.0, 15500.0])) < 400.0


def test_determinant_is_negative_left_handed_world():
    """与 perspective._solve_poses 同约定：det(R) = -1。"""
    K, R, t = cam()
    _, R2, _, _ = SP.solve_camera_plane(synth(K, R, t, FLOOR), WH)
    assert np.linalg.det(R2) < 0


def test_points_end_up_in_front_of_camera():
    K, R, t = cam()
    corr = synth(K, R, t, FLOOR)
    _, R2, t2, _ = SP.solve_camera_plane(corr, WH)
    W = np.array([c[0] for c in corr], float)
    assert (W @ R2.T + t2)[:, 2].min() > 0


# ------------------------------------------------- 退化边界（本模块的核心断言）

def _wall_corr(cam_xyz, look_at, noise=1.0):
    """北墙 (y=10200) 的 4 角，当作一个平面来标定。"""
    K, R, t = make_camera(f=F, cx=WH[0] / 2, cy=WH[1] / 2,
                          cam_xyz=cam_xyz, look_at=look_at)
    # 6 个点：留一自检至少要 5 个
    wall = [(12150.0, 10200.0, 0.0), (18150.0, 10200.0, 0.0),
            (18150.0, 10200.0, 2700.0), (12150.0, 10200.0, 2700.0),
            (14300.0, 10200.0, 0.0), (15150.0, 10200.0, 2700.0)]
    return synth(K, R, t, wall, noise_px=noise, seed=4)


def _wall_routes(corr):
    """把墙面点重参数化成 (x, z) 平面, 返回两路 f 估计(含留一稳定性)。"""
    plane = [((w[0], w[2], 0.0), p) for w, p in corr]
    return SP.focal_estimates(plane, WH[0] / 2, WH[1] / 2)


def _stable(routes):
    return [r for r in routes if r["stable"]]


def test_head_on_wall_yields_absurd_focal_and_no_route_is_stable():
    """正对墙：**不是解不出，是解出荒谬值却不报错** —— 留一稳定性必须拦住它。

    这正是 b3「错得看不出来」的同型病：朴素实现会静默返回一个错焦距。
    """
    routes = _wall_routes(_wall_corr((15150.0, 13000.0, 1400.0), (15150.0, 10200.0, 1400.0)))
    assert _stable(routes) == [], "正对位形不得有任何一路被判可信"
    solved = [r["f"] for r in routes if r["f"]]
    assert solved and min(abs(x - F) / F for x in solved) > 1.0, "该位形解出的 f 应是荒谬的"


def test_yaw_only_wall_keeps_the_accurate_route_and_drops_the_bad_one():
    """只偏航：route1(正交) 病态、route2(等模长) 准确 -> 精确保留后者。"""
    routes = _wall_routes(_wall_corr((19000.0, 13500.0, 1400.0), (14000.0, 10200.0, 1400.0)))
    st = _stable(routes)
    assert len(st) == 1 and abs(st[0]["f"] - F) / F < 0.05


def test_pitch_only_wall_drops_the_175pct_route():
    """只俯仰：一路 +176% 一路 +0.5% -> 坏的那路必须被稳定性判据剔除。"""
    routes = _wall_routes(_wall_corr((15150.0, 13000.0, 2400.0), (15150.0, 10200.0, 800.0)))
    st = _stable(routes)
    assert st and all(abs(r["f"] - F) / F < 0.05 for r in st)


def test_wall_with_both_yaw_and_pitch_gets_two_agreeing_routes():
    """偏航+俯仰 -> 两路都稳定且一致。证明退化的是**正对**而非**共面**。"""
    routes = _wall_routes(_wall_corr((19000.0, 13500.0, 2200.0), (14000.0, 10200.0, 900.0)))
    st = _stable(routes)
    assert len(st) == 2 and all(abs(r["f"] - F) / F < 0.05 for r in st)


def test_stability_criterion_never_accepts_a_bad_estimate():
    """跨焦距 x 画幅的总闸：任何被判 stable 的估计，误差都必须 < 5%。

    这条是本模块的安全性主张本身。实测 4 焦距 x 3 画幅 x 4 位形 = 32 组，
    错误采信 0 次。
    """
    wall_cfgs = (((15150.0, 13000.0, 1400.0), (15150.0, 10200.0, 1400.0)),
                 ((19000.0, 13500.0, 2200.0), (14000.0, 10200.0, 900.0)),
                 ((19000.0, 13500.0, 1400.0), (14000.0, 10200.0, 1400.0)))
    for f_true, wh in ((900.0, (2048, 1536)), (410.0, (1024, 768)), (2200.0, (4032, 3024))):
        for cam_xyz, look in wall_cfgs:
            K, R, t = make_camera(f=f_true, cx=wh[0] / 2, cy=wh[1] / 2,
                                  cam_xyz=cam_xyz, look_at=look)
            wall = [(12150.0, 10200.0, 0.0), (18150.0, 10200.0, 0.0),
                    (18150.0, 10200.0, 2700.0), (12150.0, 10200.0, 2700.0),
                    (14300.0, 10200.0, 0.0), (15150.0, 10200.0, 2700.0)]
            corr = synth(K, R, t, wall, noise_px=1.0, seed=4)
            plane = [((w[0], w[2], 0.0), p) for w, p in corr]
            for r in SP.focal_estimates(plane, wh[0] / 2, wh[1] / 2):
                if r["stable"]:
                    assert abs(r["f"] - f_true) / f_true < 0.05, (
                        f"f={f_true} wh={wh} 位形={cam_xyz}: 判 stable 却错 "
                        f"{(r['f'] - f_true) / f_true * 100:+.0f}%")


def test_floor_is_never_degenerate_across_normal_viewpoints():
    """地面在各种正常机位下都可解 —— 这是选它当真值基底的理由。"""
    for cxy in ((17000.0, 15500.0), (12500.0, 13800.0), (15000.0, 15000.0)):
        for h in (1200.0, 1500.0, 1750.0):
            K, R, t = cam(cam_xyz=(cxy[0], cxy[1], h),
                          look_at=(14500.0, 11000.0, 1000.0))
            K2, _, _, _ = SP.solve_camera_plane(synth(K, R, t, FLOOR, noise_px=1.0, seed=2), WH)
            assert abs(K2[0, 0] - F) / F < 0.06, f"机位 {cxy} 高 {h} 解崩了"


# ------------------------------------------------------------------ 拒解

def test_collinear_floor_points_rejected():
    K, R, t = cam()
    line = [(12150.0 + i * 1200.0, 10200.0, 0.0) for i in range(6)]
    with pytest.raises(ValueError, match="共线|不稳定|不可信"):
        SP.solve_camera_plane(synth(K, R, t, line), WH)


def test_too_few_points_rejected():
    K, R, t = cam()
    with pytest.raises(ValueError, match=">=5"):
        SP.solve_camera_plane(synth(K, R, t, FLOOR[:3]), WH)


def test_non_floor_points_rejected():
    K, R, t = cam()
    mixed = FLOOR[:5] + [(12150.0, 10200.0, 2700.0)]
    with pytest.raises(ValueError, match="z=0"):
        SP.solve_camera_plane(synth(K, R, t, mixed), WH)


# ------------------------------------------------------------------ 留一法

def test_leave_one_out_tracks_noise():
    K, R, t = cam()
    out = []
    for noise in (0.0, 1.0, 3.0):
        corr = synth(K, R, t, FLOOR, noise_px=noise, seed=9)
        out.append(SP.leave_one_out_plane(corr, WH)["median_px"])
    assert out[0] < 0.05
    assert out[0] < out[1] < out[2], f"留出误差未随噪声上升: {out}"


def test_leave_one_out_needs_five_points():
    K, R, t = cam()
    with pytest.raises(ValueError, match=">=5"):
        SP.leave_one_out_plane(synth(K, R, t, FLOOR[:4]), WH)


def test_holdout_exceeds_fit_under_noise():
    K, R, t = cam()
    corr = synth(K, R, t, FLOOR, noise_px=2.0, seed=6)
    K2, R2, t2, _ = SP.solve_camera_plane(corr, WH)
    fit = float(np.median(S.reproj_errors(K2, R2, t2, corr)))
    held = SP.leave_one_out_plane(corr, WH)["median_px"]
    assert held > fit


# ------------------------------------------------------------------ 自检信号

def test_self_check_info_is_reported():
    K, R, t = cam()
    _, _, _, info = SP.solve_camera_plane(synth(K, R, t, FLOOR, noise_px=0.5, seed=3), WH)
    assert len(info["routes"]) == 2
    assert info["n_stable"] >= 1
    for r in info["routes"]:
        assert {"route", "f", "cv_pct", "stable"} <= set(r)
