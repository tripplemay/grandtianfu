"""calib-route-a1 F001 — 由三组正交直线求 R/f 的验证。

与 solve_plane 一样，核心断言不只是「能解」，还包括**坏输入必须被拦住**。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import solve as S           # noqa: E402
import vp_camera as VP      # noqa: E402
from test_solve import make_camera  # noqa: E402

WH = (2048, 1536)
F = 900.0
CEIL = 2700.0


def cam(**kw):
    kw.setdefault("f", F)
    kw.setdefault("cx", WH[0] / 2)
    kw.setdefault("cy", WH[1] / 2)
    kw.setdefault("cam_xyz", (17000.0, 15500.0, 1500.0))
    kw.setdefault("look_at", (14000.0, 11000.0, 1200.0))
    return make_camera(**kw)


def project_seg(K, R, t, p0, p1):
    """投影一条世界线段。**两端都须在相机前方** —— 背后的点会投出镜像垃圾坐标
    (b3 F009 同款坑)，那种「线」不是真线，夹具不得产出。返回 None 表示不可用。
    """
    W = np.array([p0, p1], float)
    if (W @ R.T + t)[:, 2].min() <= 1.0:
        return None
    uv = S.project(K, R, t, W)
    return ((float(uv[0][0]), float(uv[0][1])), (float(uv[1][0]), float(uv[1][1])))


def room_lines(K, R, t, noise_px=0.0, seed=0, n_per_axis=3):
    """一间房的墙脚/墙顶/竖角线，按世界方向分成三组。"""
    rng = np.random.default_rng(seed)
    x0, x1, y0, y1 = 12150.0, 18150.0, 10200.0, 14100.0
    g = {"x": [], "y": [], "z": []}
    add = lambda k, seg: g[k].append(seg) if seg is not None else None
    # X 方向（东西）：南北墙的墙脚线与墙顶线
    for y in (y0, y1):
        for z in (0.0, CEIL)[:max(1, n_per_axis - 1)]:
            add("x", project_seg(K, R, t, (x0, y, z), (x1, y, z)))
    add("x", project_seg(K, R, t, (x0, y1, CEIL), (x1, y1, CEIL)))
    # Y 方向（南北）：东西墙的墙脚线与墙顶线
    for x in (x0, x1):
        add("y", project_seg(K, R, t, (x, y0, 0.0), (x, y1, 0.0)))
        add("y", project_seg(K, R, t, (x, y0, CEIL), (x, y1, CEIL)))
    # Z 方向（竖直）：墙角竖线
    for (x, y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        add("z", project_seg(K, R, t, (x, y, 0.0), (x, y, CEIL)))
    if noise_px:
        g = {k: [tuple((px + rng.normal(0, noise_px), py + rng.normal(0, noise_px))
                       for px, py in seg) for seg in v] for k, v in g.items()}
    return g


# ------------------------------------------------------------------ 精度

def test_recovers_focal_and_rotation_noiseless():
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t), WH)
    assert abs(out["f"] - F) / F < 1e-3
    assert VP.angle_between_rotations_deg(out["R"], R) < 0.1


@pytest.mark.parametrize("noise,f_lim,r_lim", [(0.0, 0.002, 0.1), (1.0, 0.03, 1.0), (3.0, 0.08, 2.5)])
def test_accuracy_degrades_gracefully(noise, f_lim, r_lim):
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t, noise_px=noise, seed=5), WH)
    assert abs(out["f"] - F) / F < f_lim
    assert VP.angle_between_rotations_deg(out["R"], R) < r_lim


def test_determinant_is_negative_left_handed_world():
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t), WH)
    assert out["det_R"] < 0
    assert np.linalg.det(out["R"]) < 0


def test_works_across_viewpoints():
    for cxy in ((17000.0, 15500.0), (12800.0, 13500.0), (16000.0, 10800.0)):
        for h in (1200.0, 1600.0):
            K, R, t = cam(cam_xyz=(cxy[0], cxy[1], h), look_at=(15000.0, 12000.0, 1100.0))
            out = VP.solve_from_lines(room_lines(K, R, t, noise_px=1.0, seed=3), WH)
            assert abs(out["f"] - F) / F < 0.05, f"机位 {cxy}/{h} 焦距解崩"
            assert VP.angle_between_rotations_deg(out["R"], R) < 1.5


# ------------------------------------------------------------------ 消失点

def test_vanishing_point_needs_two_lines():
    with pytest.raises(ValueError, match=">=2"):
        VP.vanishing_point([((0.0, 0.0), (1.0, 1.0))])


def test_parallel_image_lines_give_vp_at_infinity():
    """图上仍平行的世界平行线 -> 消失点在无穷远（w≈0），不得当成有限点去除。"""
    v = VP.vanishing_point([((0.0, 0.0), (100.0, 0.0)), ((0.0, 50.0), (100.0, 50.0))])
    assert abs(v[2]) < 1e-9


def test_vp_stability_is_none_with_fewer_than_three_lines():
    """2 条线时无从留一 —— 必须返回 None（『无法自检』），不得谎称稳定。"""
    K, R, t = cam()
    g = room_lines(K, R, t)
    assert VP.vp_stability(g["z"][:2], WH[0] / 2, WH[1] / 2) is None


def test_vp_stability_is_diagnostic_only_not_a_gate():
    """留一稳定性**不再当闸门**, 只作诊断输出。

    实测三次: (1) 分不开「混入一条错标线」与正常噪声(区间重叠); (2) 用方位角度量
    时消失点靠近主点会把 200px 抖动放大成 11° 假警报; (3) 用三维方向度量时干净数据
    仍报 60~85° 假警报。一个反复误报的闸门比没有闸门更糟 —— 它训练人忽略告警。
    把关交给已验证的逐条残差 + 消失点定位。
    """
    assert not hasattr(VP, "VP_STABILITY_LIMIT_DEG"), "该阈值已废弃, 不应复活"
    K, R, t = cam()
    g = room_lines(K, R, t, noise_px=0.5, seed=2)
    out = VP.solve_from_lines(g, WH)
    for k in VP.AXES:                       # 仍如实输出, 供报告参考
        assert k in out["vp_stability_deg"]


# ------------------------------------------------------------------ 拒解

def test_missing_direction_rejected():
    K, R, t = cam()
    g = room_lines(K, R, t)
    g["z"] = g["z"][:1]
    with pytest.raises(ValueError, match="不足 2 条线"):
        VP.solve_from_lines(g, WH)


@pytest.mark.parametrize("noise", [0.0, 1.0, 3.0, 5.0])
def test_mislabelled_line_is_caught_by_per_line_residual(noise):
    """把一条 Y 向线错标成 X 向 —— 人工画线最现实的出错方式, 必须被拦住。

    ⚠ 这条**只能靠逐条残差抓**: 实测在 3~5px 的人工噪声下, 正确分组的消失点
    留一稳定性(0.7~1.25°)与污染后(~1.3°)区间重叠, 聚合指标分不开; 而错标线的
    逐条残差是 26° vs 正确线 <0.4°, 判别比 13 倍。
    """
    K, R, t = cam()
    g = room_lines(K, R, t, noise_px=noise, seed=1)
    g["x"] = g["x"] + [g["y"][0]]
    with pytest.raises(ValueError, match="方向标错"):
        VP.solve_from_lines(g, WH)


def test_error_message_names_the_offending_line():
    """必须指出**是哪一条**, 否则用户无从改正。"""
    K, R, t = cam()
    g = room_lines(K, R, t, noise_px=1.0, seed=1)
    g["x"] = g["x"] + [g["y"][0]]
    with pytest.raises(ValueError) as ei:
        VP.solve_from_lines(g, WH)
    assert f"x组第{len(g['x'])}条" in str(ei.value)


def test_correct_lines_pass_residual_gate_even_at_human_noise():
    """5px 端点噪声(人工画线的量级)下, 正确分组不得被误拦。"""
    K, R, t = cam()
    for seed in range(5):
        out = VP.solve_from_lines(room_lines(K, R, t, noise_px=5.0, seed=seed), WH)
        assert out["max_line_residual_deg"] < VP.LINE_RESIDUAL_LIMIT_DEG


def test_outliers_are_reported_not_silently_dropped():
    """刻意不自动剔除: 少数派未必是错的。"""
    K, R, t = cam()
    g = room_lines(K, R, t, noise_px=1.0, seed=1)
    g["x"] = g["x"] + [g["y"][0]]
    with pytest.raises(ValueError, match="不自动剔除"):
        VP.solve_from_lines(g, WH)


def _rot(seg, deg):
    a = math.radians(deg)
    (x1, y1), (x2, y2) = seg
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    def r(x, y):
        dx, dy = x - mx, y - my
        return (mx + dx * math.cos(a) - dy * math.sin(a),
                my + dx * math.sin(a) + dy * math.cos(a))
    return (r(x1, y1), r(x2, y2))


@pytest.mark.parametrize("axis", ["x", "y"])
def test_corrupting_an_axis_that_determines_R_is_caught(axis):
    """x / y 组决定 R，它们被弄脏必须被拦住。"""
    K, R, t = cam()
    g = room_lines(K, R, t)
    g[axis] = [_rot(s, 8.0) if i == 0 else s for i, s in enumerate(g[axis])]
    with pytest.raises(ValueError):
        VP.solve_from_lines(g, WH)


def test_z_group_only_fixes_the_sign_and_does_not_corrupt_R():
    """**z 消失点不参与 R 的构造** —— R = [dx, dy, -cross(dx,dy)]，z 只用来定符号。

    继承自 perspective._solve_poses 的稳健性质：竖直线画歪了也毁不掉姿态。
    这里把它钉住，防止有人「优化」成三轴对称使用而引入新的脆弱点。
    """
    K, R, t = cam()
    g = room_lines(K, R, t)
    clean = VP.solve_from_lines(g, WH)
    g2 = dict(g)
    g2["z"] = [_rot(s, 12.0) for s in g["z"]]
    dirty = VP.solve_from_lines(g2, WH)
    assert VP.angle_between_rotations_deg(dirty["R"], clean["R"]) < 0.5
    assert abs(dirty["f"] - clean["f"]) / clean["f"] < 0.02


# ------------------------------------------------------------- 自检信息

def test_rotation_is_only_determined_up_to_axis_sign():
    """消失点给的是轴的**直线**不是**方向** -> R 只到符号翻转。

    这是本方法的固有边界, 不是 bug: 不商掉歧义时同一姿态会被算成相差 180°。
    产品要真用这台相机, 符号必须靠 >=1 个锚点定下来（= 位置求解, 本批推迟）。
    """
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t), WH)
    assert VP.angle_between_rotations_deg(out["R"], R) < 0.1
    raw = VP.angle_between_rotations_deg(out["R"], R, modulo_sign_ambiguity=False)
    assert raw > 90.0, f"本用例前提: 未消歧时确实差很远, 实得 {raw:.1f}°"


def test_sign_variants_are_four_and_all_left_handed():
    K, R, t = cam()
    vs = VP.canonical_variants(R)
    assert len(vs) == 4
    assert all(np.linalg.det(V) < 0 for V in vs)
    assert any(np.allclose(V, R, atol=1e-9) for V in vs), "原姿态须在等价类里"


def test_reports_self_check_details():
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t, noise_px=0.5, seed=4), WH)
    assert out["self_checked"] is True          # 每轴 >=3 条线 -> 残差与稳定性可算
    assert len(out["f_per_pair"]) >= 2
    assert out["f_pairs_used"], "至少要有一对被采信"
    for k in VP.AXES:
        assert out["vp_stability_deg"][k] is not None
        assert out["n_lines"][k] >= 2
        assert out["vp_localization"][k] > 0


def test_cross_checked_false_when_only_one_pair_is_well_localized():
    """真实室内照的常态：竖直消失点很远, 只剩 xy 一对可信 -> 无从跨对核对。

    此时 f 仍可信（xy 对实测恒 ±0.2%），但必须**如实标注 cross_checked=False**,
    不得让报告读者以为有冗余印证。
    """
    K, R, t = cam()
    out = VP.solve_from_lines(room_lines(K, R, t, noise_px=0.5, seed=4), WH)
    if len(out["f_pairs_used"]) == 1:
        assert out["cross_checked"] is False


def test_self_checked_false_when_only_two_lines_per_axis():
    """每轴只有 2 条线 -> 解得出但**无法自检**, 必须如实标注。"""
    K, R, t = cam()
    g = {k: v[:2] for k, v in room_lines(K, R, t).items()}
    out = VP.solve_from_lines(g, WH)
    assert out["self_checked"] is False


# ------------------------------------------------- 「自动 vs 人工」的度量本身

def test_rotation_angle_metric_is_zero_for_identical_and_grows():
    K, R, t = cam()
    assert VP.angle_between_rotations_deg(R, R) < 1e-4   # acos 在 1 附近的数值下限
    K2, R2, t2 = cam(look_at=(14000.0, 11000.0, 1600.0))
    d = VP.angle_between_rotations_deg(R, R2)
    assert 0.1 < d < 40.0
