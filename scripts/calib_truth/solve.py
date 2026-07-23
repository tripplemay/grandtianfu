"""calib-route-a1 F001 — 真值相机求解器（DLT + 高斯牛顿细化 + 留一法）。

**为什么不复用 apps/api/aigc/perspective.calibrate()：** 真值必须独立于被测对象。
复用产品求解器 = 真值继承产品的 bug，那就不叫真值了。本模块只与产品**约定**对齐
（世界系、K 形式），求解过程完全独立重写。

**世界系约定（与产品逐字一致，见 perspective.py 的两世界警告）：**
  X = 东(+)，Y = 南(+)，Z = 上(+)，单位 mm；地面 z=0，天花 z=2700。
  该系是**左手系**（East × South = Down），故物理正确的 R 满足 **det(R) = -1**。
  ⚠ 用 SVD 投影到 SO(3)（强制 det=+1）会把相机解到地板下方 —— 那正是 calib-z-b1
  的根因，本模块以 `det<0` 为**期望**而非错误。

纯 numpy（本机无 scipy，且 api 的 requirements 也只有 numpy）。
"""
from __future__ import annotations

import numpy as np

Corr = tuple[tuple[float, float, float], tuple[float, float]]


# ---------------------------------------------------------------- 基础分解

def _rq3(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """3x3 的 RQ 分解 M = R_upper @ Q_orth（numpy 只有 QR，故做翻转技巧）。"""
    P = np.flipud(np.eye(3))
    Q_, R_ = np.linalg.qr((P @ M).T)
    R = P @ R_.T @ P
    Q = P @ Q_.T
    # 规范化：让 R 的对角为正（吸收符号到 Q）
    S = np.diag(np.sign(np.diag(R)) + (np.diag(R) == 0))
    return R @ S, S @ Q


def _normalize(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hartley 归一化：均值移到原点，均方距离 -> sqrt(dim)。返回 (归一化点, T)。"""
    d = pts.shape[1]
    c = pts.mean(0)
    s = np.sqrt(d) / (np.linalg.norm(pts - c, axis=1).mean() + 1e-12)
    T = np.eye(d + 1)
    T[:d, :d] *= s
    T[:d, d] = -s * c
    hom = np.hstack([pts, np.ones((len(pts), 1))])
    return (hom @ T.T)[:, :d], T


def dlt(corr: list[Corr]) -> np.ndarray:
    """线性 DLT 求 3x4 投影矩阵 P（需 >=6 个**非共面**对应）。"""
    if len(corr) < 6:
        raise ValueError(f"DLT 需 >=6 个对应, 收到 {len(corr)}")
    W = np.array([c[0] for c in corr], float)
    U = np.array([c[1] for c in corr], float)
    if np.linalg.matrix_rank(W - W.mean(0), tol=1e-6) < 3:
        raise ValueError(
            "世界点共面（秩<3）——DLT 退化, 无法定相机。"
            "这正是 b2/b3 反复踩的坑：请补入不同高度的点（天花角/门头）。"
        )
    Wn, Tw = _normalize(W)
    Un, Tu = _normalize(U)
    A = np.zeros((2 * len(corr), 12))
    for i, ((X, Y, Z), (u, v)) in enumerate(zip(Wn, Un)):
        A[2 * i] = [X, Y, Z, 1, 0, 0, 0, 0, -u * X, -u * Y, -u * Z, -u]
        A[2 * i + 1] = [0, 0, 0, 0, X, Y, Z, 1, -v * X, -v * Y, -v * Z, -v]
    P = np.linalg.svd(A)[2][-1].reshape(3, 4)
    return np.linalg.inv(Tu) @ P @ Tw          # 反归一化


def decompose(P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P -> (K, R, t)。**保留 det(R) 的符号**（左手世界系下期望 -1）。"""
    K, R = _rq3(P[:, :3])
    t = np.linalg.inv(K) @ P[:, 3]
    if K[2, 2] < 0:                            # 整体符号归一
        K, R, t = -K, -R, -t
    K = K / K[2, 2]
    if K[0, 0] < 0:                            # 焦距须为正
        F = np.diag([-1.0, 1.0, 1.0])
        K, R, t = K @ F, F @ R, F @ t
    if K[1, 1] < 0:
        F = np.diag([1.0, -1.0, 1.0])
        K, R, t = K @ F, F @ R, F @ t
    return K, R, t


# ---------------------------------------------------------------- 细化

def _skew(w: np.ndarray) -> np.ndarray:
    return np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])


def _expm_so3(w: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    K = _skew(w / th)
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)


def project(K, R, t, W: np.ndarray) -> np.ndarray:
    c = W @ R.T + t
    return (c @ K.T)[:, :2] / c[:, 2:3]


def _pack(f, cx, cy, w, t):
    return np.concatenate([[f, cx, cy], w, t])


def refine(K, R0, t, corr: list[Corr], *, iters=60, fix_pp=False):
    """高斯牛顿最小化重投影残差。

    相机模型与产品一致：K = [[f,0,cx],[0,f,cy],[0,0,1]]（方像素、无 skew）。
    姿态参数化 R = R0 @ expm(skew(w))：expm ∈ SO(3) 恒 det=+1，故 **det(R) 的符号
    在整个优化过程中被保住**，不会翻到地板下方。
    """
    W = np.array([c[0] for c in corr], float)
    U = np.array([c[1] for c in corr], float)
    f = float((K[0, 0] + K[1, 1]) / 2)
    p = _pack(f, K[0, 2], K[1, 2], np.zeros(3), t)

    def unpack(p):
        f, cx, cy = p[0], p[1], p[2]
        Kk = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
        return Kk, R0 @ _expm_so3(p[3:6]), p[6:9]

    def resid(p):
        Kk, Rr, tt = unpack(p)
        return (project(Kk, Rr, tt, W) - U).ravel()

    free = [0, 3, 4, 5, 6, 7, 8] if fix_pp else list(range(9))
    r = resid(p)
    for _ in range(iters):
        J = np.zeros((len(r), len(free)))
        for j, k in enumerate(free):
            h = max(1e-6, abs(p[k]) * 1e-6)
            q = p.copy()
            q[k] += h
            J[:, j] = (resid(q) - r) / h
        try:
            dp = np.linalg.lstsq(J, -r, rcond=None)[0]
        except np.linalg.LinAlgError:
            break
        q = p.copy()
        q[free] += dp
        rq = resid(q)
        if np.linalg.norm(rq) >= np.linalg.norm(r) - 1e-12:
            break
        p, r = q, rq
    return unpack(p)


def enforce_cheirality(K, R, t, corr: list[Corr]):
    """用「点必须在相机前方」消解 P 与 -P 的符号歧义。

    P 和 -P 给出**完全相同**的像素投影，故 DLT 无法区分 (K,R,t) 与 (K,-R,-t)；
    唯一的判据是物理的：世界点的相机系深度须 > 0。

    ⚠ 注意 det(-R) = -det(R) —— 手性由这一步**自动定下**，不该另行强制。
    这也是本模块不用 SVD 投影到 SO(3) 的原因（那会绕过物理判据去硬拗符号，
    正是 calib-z-b1 把相机解到地板下方的根因）。
    """
    W = np.array([c[0] for c in corr], float)
    if (W @ R.T + t)[:, 2].sum() < 0:
        R, t = -R, -t
    return K, R, t


def solve_camera(corr: list[Corr], *, fix_pp=False):
    """完整求解：DLT -> 前方性消歧 -> 细化。返回 (K, R, t)。"""
    K, R, t = decompose(dlt(corr))
    K, R, t = enforce_cheirality(K, R, t, corr)
    return refine(K, R, t, corr, fix_pp=fix_pp)


# ---------------------------------------------------------------- 误差与留一法

def reproj_errors(K, R, t, corr: list[Corr]) -> np.ndarray:
    W = np.array([c[0] for c in corr], float)
    U = np.array([c[1] for c in corr], float)
    return np.linalg.norm(project(K, R, t, W) - U, axis=1)


def leave_one_out(corr: list[Corr], *, fix_pp=False) -> dict:
    """留一法交叉验证 —— **留出点的重投影误差即该真值的不确定度**（spec §D1）。

    对每个 i：用其余 n-1 点解相机，再把点 i 投影，量它离人工标注的像素距离。
    这个数字回答的是「这台参考相机对一个它没见过的点能预测多准」，而不是
    「它把训练点拟合得多好」——后者可以靠过拟合刷低，前者不能。
    """
    n = len(corr)
    if n < 7:
        raise ValueError(f"留一法需 >=7 个对应（留一后仍须 >=6 供 DLT）, 收到 {n}")
    held, failed = [], []
    for i in range(n):
        rest = corr[:i] + corr[i + 1:]
        try:
            K, R, t = solve_camera(rest, fix_pp=fix_pp)
        except (ValueError, np.linalg.LinAlgError) as e:
            failed.append({"index": i, "reason": str(e)})
            continue
        held.append(float(reproj_errors(K, R, t, [corr[i]])[0]))
    if not held:
        raise ValueError("留一法全部失败, 该组对应无法支撑真值")
    a = np.array(held)
    return {
        "n": n,
        "n_evaluated": len(held),
        "n_failed": len(failed),
        "failures": failed,
        "holdout_px": [round(x, 2) for x in held],
        "median_px": round(float(np.median(a)), 2),
        "mean_px": round(float(a.mean()), 2),
        "max_px": round(float(a.max()), 2),
        "p90_px": round(float(np.percentile(a, 90)), 2),
    }
