"""calib-route-a1 F001 — 单平面（地面）标定：只用可信世界坐标。

**为什么只用地面：** 平面图可靠知道的只有**水平尺寸**。竖直坐标全是假设 ——
层高 2700 (`perspective._REAL_CEILING_MM`，文档自承只验了方向未量过数值)、
门头 2050 (常量)、窗台高度 (geometry 里根本没有)。拿假设当世界坐标去建"真值"，
建出来的不是真值。地面点则是零假设：x/y 来自平面图，z=0 是地面的定义。

**退化边界（合成实测，见 tests/test_solve_plane.py）：** 单应给出**两路独立的
f 估计** —— 正交约束一路、等模长约束一路。两路各自的可解性取决于平面的两个面内
方向是否被透视压缩（h1z / h2z 是否非零）：

    位形              两路 f                       自检门
    地面·站立俯看      +0.2% / +0.7%   两路一致      **过**
    墙·偏航+俯仰      +1.0% / -0.4%   两路一致      过
    墙·只偏航         -0.3%           仅一路        拒（保守误拒：准但不敢用）
    墙·只俯仰         +176% / +0.5%   两路矛盾      拒
    墙·正对          **+930%**        仅一路        拒

⚠ 关键：正对位形**不是解不出，而是解出一个 +930% 的荒谬 f** —— b3「错得看不出来」
的同型病。安全性不来自「算不出来就会报错」，而来自**自检门要求两路互相印证**。
门在上表中从未接受过错解，代价只是误拒了「只偏航」那一个准解。

地面在任何正常室内照里都被两向压缩（相机在地面之上、略微俯视），故恒过门 ——
这正是选它当真值基底的原因。（唯一例外是正上方垂直俯拍地面，室内照不会出现。）

⚠ 顺带订正一条既有归因：calib-cure-b2 把失败归因于「特征共面 -> 几何退化」。
共面**不是**原因（本模块正是靠共面点工作的），**平面正对相机**才是。该订正尚未
用真实数据验证，按用户裁决暂不据此改动产品。
"""
from __future__ import annotations

import math

import numpy as np

import solve as S

PlaneCorr = tuple[tuple[float, float, float], tuple[float, float]]

# ---------------------------------------------------------------- 自检门参数
#
# 单路 f 估计的稳定性上限：留一法下该路 f 的变异系数。**不用条件数阈值** ——
# 实测条件数随画幅系统性漂移（4032x3024 与 1024x768 差一个量级），绝对阈值跨
# 画幅误判；留一法 CV 是无量纲的，实测在 4 种焦距 x 3 种画幅下几乎不变
# （正对位形恒为 42%/56%）。
F_STABILITY_LIMIT_CV_PCT = 10.0
# 两路都稳定时，它们还须互相印证。
F_CONSISTENCY_LIMIT_PCT = 15.0


def _homography(corr: list[PlaneCorr]) -> np.ndarray:
    """地面点 (x, y, 0) -> 像素 的单应矩阵（Hartley 归一化 DLT）。"""
    if len(corr) < 4:
        raise ValueError(f"单平面标定需 >=4 个地面点, 收到 {len(corr)}")
    W = np.array([c[0] for c in corr], float)
    if not np.allclose(W[:, 2], 0.0):
        raise ValueError("solve_plane 只接受 z=0 的地面点")
    U = np.array([c[1] for c in corr], float)
    P = W[:, :2]
    if np.linalg.matrix_rank(P - P.mean(0), tol=1e-6) < 2:
        raise ValueError("地面点共线 —— 单应不可解, 请标不在同一条直线上的点")
    Pn, Tw = S._normalize(P)
    Un, Tu = S._normalize(U)
    A = []
    for (X, Y), (u, v) in zip(Pn, Un):
        A.append([X, Y, 1, 0, 0, 0, -u * X, -u * Y, -u])
        A.append([0, 0, 0, X, Y, 1, -v * X, -v * Y, -v])
    H = np.linalg.svd(np.array(A))[2][-1].reshape(3, 3)
    return np.linalg.inv(Tu) @ H @ Tw


def focal_candidates(H: np.ndarray, cx: float, cy: float) -> list[float]:
    """由单应的两条独立约束各解一次 f（**不含稳定性判断**，见 focal_estimates）。

    以主点为原点后 ω = diag(1/f², 1/f², 1)：
      route1 正交   h1ᵀ ω h2 = 0        -> f² = -(h1x·h2x + h1y·h2y) / (h1z·h2z)
      route2 等模长 h1ᵀ ω h1 = h2ᵀ ω h2 -> f² = ((h2x²+h2y²) - (h1x²+h1y²)) / (h1z² - h2z²)

    ⚠ 这两个式子在平面接近正对时分母趋零，会**吐出荒谬值而不报错**（实测正对
    墙面得到 +3754% 的 f）。故绝不可直接采信本函数的返回值，必须经
    focal_estimates 的留一稳定性筛。
    """
    T = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1.0]])
    Hc = T @ H
    h1, h2 = Hc[:, 0], Hc[:, 1]
    out: list[float] = []
    for num, den in (
        (-(h1[0] * h2[0] + h1[1] * h2[1]), h1[2] * h2[2]),
        ((h2[0] ** 2 + h2[1] ** 2) - (h1[0] ** 2 + h1[1] ** 2), h1[2] ** 2 - h2[2] ** 2),
    ):
        f2 = num / den if den else None
        out.append(math.sqrt(f2) if (f2 is not None and 1e2 < f2 < 1e9) else None)
    return out


def focal_estimates(corr: list[PlaneCorr], cx: float, cy: float) -> list[dict]:
    """两路 f 估计，各自用**留一法量稳定性**决定可否采信。

    为什么用留一 CV 而不是条件数：病态位形的 f 会随着去掉任一个点而剧烈摆动，
    良态的不会 —— 这个量无量纲，跨画幅稳定。实测（4 焦距 x 3 画幅 x 4 位形）：

        位形            route1 CV / 误差      route2 CV / 误差
        墙·正对         42%  / +3754%         56%  / +1141%     两路皆拒
        墙·偏航+俯仰    1.2% / +0.9%          0.4% / -0.4%      两路皆取
        地面·有偏航     43%  / +0.1%          0.3% / +0.7%      取 route2
        地面·无偏航     320% / +9.6%          0.4% / +0.4%      取 route2

    32 组里**错误采信坏解 0 次**；4 次保守误拒，但每次另一路都可用。
    """
    n = len(corr)
    per_route: list[list[float]] = [[], []]
    for i in range(n):
        rest = corr[:i] + corr[i + 1:]
        if len(rest) < 4:
            continue
        try:
            H = _homography(rest)
        except ValueError:
            continue
        for r, f in enumerate(focal_candidates(H, cx, cy)):
            if f is not None:
                per_route[r].append(f)
    out = []
    for r, fs in enumerate(per_route):
        if len(fs) < 3:                       # 样本太少，稳定性无从谈起
            out.append({"route": r + 1, "f": None, "cv_pct": None, "stable": False})
            continue
        a = np.array(fs)
        med = float(np.median(a))
        cv = float(np.std(a) / med * 100) if med else float("inf")
        out.append({"route": r + 1, "f": round(med, 2), "cv_pct": round(cv, 2),
                    "stable": cv < F_STABILITY_LIMIT_CV_PCT})
    return out


def decompose_plane(H: np.ndarray, f: float, cx: float, cy: float):
    """单应 + f -> (K, R, t)。

    R 的列 = 世界轴在相机系的方向；世界系左手 (X东/Y南/Z上) 故第三列取
    **-cross(r1, r2)**，与产品 perspective._solve_poses 逐字一致，det(R) = -1。
    """
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    Ki = np.linalg.inv(K)
    M = Ki @ H
    n1, n2 = np.linalg.norm(M[:, 0]), np.linalg.norm(M[:, 1])
    lam = 2.0 / (n1 + n2)                       # 两列模长的折中，抗噪
    r1, r2 = M[:, 0] / n1, M[:, 1] / n2
    # 施密特正交化（噪声会让 r1, r2 略不正交）
    r2 = r2 - np.dot(r1, r2) * r1
    r2 /= np.linalg.norm(r2)
    r3 = -np.cross(r1, r2)                      # 左手世界系 => det(R) = -1
    R = np.column_stack([r1, r2, r3])
    t = M[:, 2] * lam
    return K, R, t


def solve_camera_plane(corr: list[PlaneCorr], img_wh, *, refine=True):
    """地面点 -> (K, R, t, info)。info 记录两路 f 估计、稳定性与交叉印证。

    自检门（三层，缺一不可）：
      1. 至少一路 f 在留一法下稳定（CV < 10%）
      2. 若两路都稳定，它们须互相印证（差异 <= 15%）
      3. 解出的相机须在地面上方、且点在相机前方（由调用方查 center/depth）
    """
    if len(corr) < 5:
        raise ValueError(
            f"自检需留一法, 故需 >=5 个地面点（单应本身只要 4 个, 但 4 个无从自检）, "
            f"收到 {len(corr)}"
        )
    # 入口处快速失败：非地面点的错误信息必须直达调用方。若留到 _homography 里再报,
    # 会被 focal_estimates 的 except ValueError 吞掉, 最后以「焦距不可信」这种
    # 指错方向的信息冒出来。
    if not np.allclose(np.array([c[0] for c in corr], float)[:, 2], 0.0):
        raise ValueError("solve_plane 只接受 z=0 的地面点")
    W_, H_ = img_wh
    cx, cy = W_ / 2.0, H_ / 2.0
    ests = focal_estimates(corr, cx, cy)
    stable = [e for e in ests if e["stable"]]
    if not stable:
        raise ValueError(
            "焦距不可信 —— 两路估计在留一法下都不稳定。该平面相对相机接近正对时"
            "会出现此情况（分母趋零, 会解出荒谬焦距却不报错）。地面点正常不该如此, "
            "请检查标注是否错配或点是否过于集中。"
        )
    spread = None
    if len(stable) == 2:
        v = [e["f"] for e in stable]
        spread = (max(v) - min(v)) / min(v) * 100
        if spread > F_CONSISTENCY_LIMIT_PCT:
            raise ValueError(
                f"两路焦距估计互不印证（{v[0]:.0f} vs {v[1]:.0f}, 差异 {spread:.1f}%）—— "
                f"该组标注不可信。"
            )
    f = float(np.mean([e["f"] for e in stable]))
    H = _homography(corr)
    K, R, t = decompose_plane(H, f, cx, cy)
    # 前方性消歧（H 的整体符号未定）
    Wm = np.array([c[0] for c in corr], float)
    if (Wm @ R.T + t)[:, 2].sum() < 0:
        R, t = -R, -t
    if refine:
        # 共面数据定不了主点, 故 fix_pp
        K, R, t = S.refine(K, R, t, corr, fix_pp=True)
    return K, R, t, {
        "routes": ests,
        "n_stable": len(stable),
        "f_spread_pct": None if spread is None else round(spread, 2),
        # 两路都稳定且一致 = 有交叉印证; 只有一路 = 能用但无冗余可查
        "cross_checked": len(stable) == 2,
        "self_consistent": True,          # 走到这里说明已过门
    }


def leave_one_out_plane(corr: list[PlaneCorr], img_wh) -> dict:
    """留一法：留出点的重投影误差 = 该真值的不确定度。

    单应需 >=4 点，故留一后仍须 >=4 => 至少 5 个标注点。
    """
    n = len(corr)
    if n < 5:
        raise ValueError(f"留一法需 >=5 个地面点（留一后仍须 >=4 供单应）, 收到 {n}")
    held, failed = [], []
    for i in range(n):
        rest = corr[:i] + corr[i + 1:]
        try:
            K, R, t, _ = solve_camera_plane(rest, img_wh)
        except (ValueError, np.linalg.LinAlgError) as e:
            failed.append({"index": i, "reason": str(e)})
            continue
        held.append(float(S.reproj_errors(K, R, t, [corr[i]])[0]))
    if not held:
        raise ValueError("留一法全部失败, 该组标注无法支撑真值")
    a = np.array(held)
    return {
        "n": n, "n_evaluated": len(held), "n_failed": len(failed), "failures": failed,
        "holdout_px": [round(x, 2) for x in held],
        "median_px": round(float(np.median(a)), 2),
        "mean_px": round(float(a.mean()), 2),
        "max_px": round(float(a.max()), 2),
        "p90_px": round(float(np.percentile(a, 90)), 2),
    }
