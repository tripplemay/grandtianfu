"""calib-route-a1 — 由三组正交方向的直线求相机 R 与 f（人工线 / 自动线共用）。

**为什么人工线与自动线共用同一套数学：** 本批要回答的是「自动找线能否达到人工
画线的水准」。让两条路走同一套 VP→(R,f) 数学，就把**线的来源**隔离成唯一变量 ——
这是受控对比，不是循环论证。数学本身的正确性另由合成数据 + EXIF 外部真值背书
（spec §6.1：自检门接受的照片 f 误差 ~1%）。

**为什么退回到画线：** 点对应在真实照片上凑不够。一个角点要求两个面的交线同时
可见、且交点落在画面内；一条直线只要那条交线露出一段就行。实测 r_study 可标角点
仅 2 个，可画直线 10+ 条。见 spec §D1.2。

世界系与产品一致：X=东, Y=南, Z=上（左手系 => det(R) = -1）。
"""
from __future__ import annotations

import math

import numpy as np

Seg = tuple[tuple[float, float], tuple[float, float]]

# 单条线与其所属消失点的一致性上限（度）。**主判据。**
#
# 实测（合成，跨噪声 1/3/5px）：正确分组的线残差最大 0.37°；混入一条方向标错的线，
# 那条的残差是 **26.4°**，判别比 13 倍。取 3° 既远高于噪声上限，又远低于错标。
LINE_RESIDUAL_LIMIT_DEG = 3.0

# ⚠ **留一稳定性不再作为闸门, 只作诊断信息输出。** 三次实测结论：
#   1. 它分不开主要失效模式：真实人工噪声(3~5px)下, 正确分组的稳定性与「混入一条
#      错标线」区间重叠(0.7~1.25° vs ~1.3°), 不存在可用阈值;
#   2. 换成「消失点方位角」度量, 消失点靠近主点时把 200px 抖动放大成 11° 假警报;
#   3. 换成「三维方向夹角」度量, 干净数据仍报出 60~85° 假警报。
# 把关交给两个**已验证**的判据: 逐条线残差(13 倍判别比) + 消失点定位(理论支撑)。
# 保留本量输出是因为它对「整组线都不平行」仍有诊断价值, 但不据此拒解 ——
# 一个反复产生假警报的闸门比没有闸门更糟, 它会训练人忽略告警。
# 消失点定位质量 = 它离主点的距离 / 图像对角线。**无量纲，跨画幅可比。**
# 越大 = 该方向在图上越接近平行 = 该消失点对焦距的约束越弱。实测竖直 VP 在
# loc≈14 时含它的正交对误差达 -8.1%，loc≈1.1 时仅 0.4%。取 6 作上限。
VP_LOCALIZATION_LIMIT = 6.0
# 通过稳定性筛之后，各对之间还须互相印证。
F_CONSISTENCY_LIMIT_PCT = 15.0
AXES = ("x", "y", "z")


def _homog(seg: Seg) -> np.ndarray:
    (x1, y1), (x2, y2) = seg
    return np.cross([x1, y1, 1.0], [x2, y2, 1.0])


def vanishing_point(segs: list[Seg]) -> np.ndarray:
    """一组平行线 -> 消失点（齐次）。取所有直线的最小奇异向量。

    平行线在图像上交于消失点；有噪声时无公共交点，最小二乘解即最小奇异向量。
    返回未归一化的齐次坐标（消失点可能在无穷远，w≈0，不可强行除）。
    """
    if len(segs) < 2:
        raise ValueError(f"求消失点需 >=2 条平行线, 收到 {len(segs)}")
    L = np.array([_homog(s) for s in segs], float)
    L = L / (np.linalg.norm(L, axis=1, keepdims=True) + 1e-12)
    return np.linalg.svd(L)[2][-1]


def line_residual_deg(seg: Seg, v: np.ndarray) -> float:
    """单条线与消失点的一致性：线的方向 vs 从其中点指向消失点的方向，夹角（度）。

    错标方向是人工画线最现实的出错方式。这个量对它极其敏感（实测错标线 26°，
    正确线 <0.4°），而聚合的消失点稳定性对它**不敏感**（会被噪声淹没）。
    """
    (x1, y1), (x2, y2) = seg
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    d = np.array([x2 - x1, y2 - y1], float)
    d /= np.linalg.norm(d) + 1e-12
    if abs(v[2]) < 1e-12:
        tv = np.array([v[0], v[1]], float)
    else:
        tv = np.array([v[0] / v[2] - mx, v[1] / v[2] - my], float)
    tv /= np.linalg.norm(tv) + 1e-12
    return math.degrees(math.acos(min(1.0, abs(float(d @ tv)))))


def group_residuals(segs: list[Seg]) -> tuple[np.ndarray, list[float]]:
    """一组线 -> (消失点, 每条线的残差度数)。"""
    v = vanishing_point(segs)
    return v, [line_residual_deg(s, v) for s in segs]


def vp_direction_deg(v: np.ndarray, cx: float, cy: float) -> float:
    """消失点相对主点的方向角（度）—— 用作留一法下 VP 稳定性的度量。

    直接比较消失点坐标不行：它常在无穷远附近，坐标数值可以剧烈跳动而方向不变。
    方向角对这种情形稳定，且正是下游 R 真正依赖的量。
    """
    if abs(v[2]) < 1e-12:
        dx, dy = v[0], v[1]
    else:
        dx, dy = v[0] / v[2] - cx, v[1] / v[2] - cy
    return math.degrees(math.atan2(dy, dx)) % 180.0


def vp_localization(v: np.ndarray, cx: float, cy: float, diag: float) -> float:
    """消失点离主点的距离 / 图像对角线 —— **无量纲的可信度指标**。

    消失点越接近无穷远（该方向的线在图上越接近平行），它对焦距的约束越弱：
    正交约束 v1ᵀωv2=0 的分母正比于两个 w 分量，w→0 时退化。
    返回 inf 表示消失点在无穷远。
    """
    if abs(v[2]) < 1e-12:
        return float("inf")
    return math.hypot(v[0] / v[2] - cx, v[1] / v[2] - cy) / diag


def vp_ray(v: np.ndarray, cx: float, cy: float, f_nominal: float) -> np.ndarray:
    """消失点 -> 它代表的三维方向（相机系单位向量）。

    这才是 R 真正依赖的量。用它度量稳定性对**远近消失点都良态**；而「消失点在
    图像上的方位角」在消失点靠近主点时会把微小抖动放大成十几度的假警报
    （实测 loc=0.4 时 200px 抖动 -> 11°）。f_nominal 只用于这个度量，不需精确。
    """
    d = np.array([v[0] - cx * v[2], v[1] - cy * v[2], f_nominal * v[2]], float)
    n = np.linalg.norm(d)
    if n < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    return d / n      # ⚠ 这是**轴**不是有向向量, 比较时须按 |cos| 处理(见 vp_stability)


def vp_stability(segs: list[Seg], cx: float, cy: float,
                 f_nominal: float | None = None) -> float | None:
    """留一法：逐条去掉一条线重算消失点，看它代表的**三维方向**摆动多大（度）。

    与点法的留一法同理 —— 拟合残差可以靠过拟合刷低，留出稳定性不能。
    少于 3 条线时无从留一，返回 None（表示「无法自检」，不等于「稳定」）。

    ⚠ 这是**辅助**判据：实测它分不开「混入一条错标线」与正常噪声（区间重叠），
    那个失效模式必须靠 line_residual_deg 抓。本项只用于发现「整组线都不平行」。
    """
    if len(segs) < 3:
        return None
    if f_nominal is None:
        f_nominal = 2.0 * max(cx, cy)
    rays = []
    for i in range(len(segs)):
        rest = segs[:i] + segs[i + 1:]
        try:
            rays.append(vp_ray(vanishing_point(rest), cx, cy, f_nominal))
        except ValueError:
            continue
    if len(rays) < 3:
        return None
    A = np.array(rays)
    # 轴的「平均」= 散布矩阵的主特征向量。直接取向量均值是错的: 消失点在无穷远
    # 附近时相邻两次解会落在对映方向, 向量均值把它们相消, 于是干净数据也报出
    # 60° 的假警报(实测)。
    m = np.linalg.eigh(A.T @ A)[1][:, -1]
    return float(max(math.degrees(math.acos(min(1.0, abs(float(r @ m))))) for r in A))


def focal_from_pair(v1: np.ndarray, v2: np.ndarray, cx: float, cy: float) -> float | None:
    """两个正交消失点 -> f。ω=diag(1/f²,1/f²,1) 下 v1ᵀωv2 = 0。

    与产品 perspective._solve_poses 同一个公式（那里写作
    f² = -(vpx-c)·(vpy-c)），此处用齐次形式以容纳无穷远消失点。
    """
    a = np.array([v1[0] - cx * v1[2], v1[1] - cy * v1[2], v1[2]])
    b = np.array([v2[0] - cx * v2[2], v2[1] - cy * v2[2], v2[2]])
    den = a[2] * b[2]
    if abs(den) < 1e-15:
        return None
    f2 = -(a[0] * b[0] + a[1] * b[1]) / den
    if not (1e2 < f2 < 1e9):
        return None
    return math.sqrt(f2)


def rotation_from_vps(vps: dict[str, np.ndarray], f: float, cx: float, cy: float) -> np.ndarray:
    """三个正交消失点 + f -> R（列 = 世界轴在相机系的方向）。

    ⚠ 世界系 (X东,Y南,Z上) 相对物理空间是左手的，物理正确的 R **必然 det = -1**；
    第三列取 -cross(ex,ey)，与 perspective._solve_poses 逐字一致。用 SVD 强行投影到
    SO(3)（det=+1）会把相机解到地板下方 —— calib-z-b1 的根因。

    ⚠⚠ **符号歧义（本方法的固有边界）**：消失点给出的是轴的**直线**，不是**有向
    方向** —— 它分不清这条线指向东还是指向西。故 R 只能定到「各轴符号翻转」的
    程度（`_solve_poses` 枚举 sx, sy ∈ {±1} 正是为此）。产品用锚点的前方性消歧，
    而锚点属于位置求解 = 本批 §D4 明确推迟的部分。

    本函数只做一件能做的事：用「相机大致正持」把 **Z 轴**的符号定下来（世界的
    「上」在图像里应当朝上，即其相机系 y 分量为负，因为图像 y 轴朝下）。
    X/Y 的符号无法从线本身定，留给 `angle_between_rotations_deg` 在比较时商掉。
    """
    d = {}
    for k in AXES:
        v = vps[k]
        vec = np.array([v[0] - cx * v[2], v[1] - cy * v[2], f * v[2]], float)
        n = np.linalg.norm(vec)
        if n < 1e-12:
            raise ValueError(f"{k} 轴消失点退化")
        d[k] = vec / n
    if d["z"][1] > 0:                 # 相机正持 => 世界「上」在图像里朝上
        d["z"] = -d["z"]
    # 让 x/y 与已定符号的 z 构成左手系的确定代表元
    if np.dot(-np.cross(d["x"], d["y"]), d["z"]) < 0:
        d["y"] = -d["y"]
    return np.column_stack([d["x"], d["y"], -np.cross(d["x"], d["y"])])


# 消失点定不了轴的指向，故 R 只到符号翻转。与 perspective._solve_poses 的
# 枚举一致：sx, sy 独立取 ±1，第三轴由 -cross 自动跟随。
_SIGN_GROUP = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def canonical_variants(R: np.ndarray) -> list[np.ndarray]:
    """R 在符号歧义下的全部等价形态（4 个）。"""
    out = []
    for sx, sy in _SIGN_GROUP:
        ex, ey = R[:, 0] * sx, R[:, 1] * sy
        out.append(np.column_stack([ex, ey, -np.cross(ex, ey)]))
    return out


def solve_from_lines(groups: dict[str, list[Seg]], img_wh) -> dict:
    """三组方向的直线 -> R, f, 以及自检结论。

    groups: {"x": [...东西向...], "y": [...南北向...], "z": [...竖直...]}

    自检（与 solve_plane 同构）：
      1. 每组 >=2 条线才有消失点；>=3 条才**能自检**（留一法）
      2. 每条线与本组消失点的残差须 < 3 度（**主判据**：抓「方向标错」）
      3. 至少一对正交的两个消失点都定位良好（loc <= 6）
      4. 可信度相当的几对正交解出的 f 须互相印证（<= 15%）
    留一稳定性只作诊断输出，不拒解 —— 理由见文件顶部常量处。
    """
    W, H = img_wh
    cx, cy = W / 2.0, H / 2.0
    missing = [k for k in AXES if len(groups.get(k, [])) < 2]
    if missing:
        raise ValueError(f"以下方向不足 2 条线, 无法求消失点: {missing}")

    # 主判据：逐条线残差。错标方向的线在这里必然暴露（实测 26° vs <0.4°）。
    vps, stab, resids, offenders = {}, {}, {}, []
    for k in AXES:
        vps[k], resids[k] = group_residuals(groups[k])
        stab[k] = vp_stability(groups[k], cx, cy)
        for i, r in enumerate(resids[k]):
            if r > LINE_RESIDUAL_LIMIT_DEG:
                offenders.append((k, i, round(r, 2)))
    if offenders:
        detail = ", ".join(f"{k}组第{i + 1}条({r}°)" for k, i, r in offenders)
        raise ValueError(
            f"以下线与本组消失点不一致（上限 {LINE_RESIDUAL_LIMIT_DEG}°）: {detail}。"
            f"最常见成因是**方向标错了**（把南北向的线标成了东西向）。请改正后重新导出 —— "
            f"此处刻意不自动剔除: 少数派未必就是错的, 该由人判断。"
        )

    # 三对正交各解一次 f，但**可信度差别极大**，取决于两个消失点离主点多远：
    # 消失点越接近无穷远（该方向的线在图上越接近平行），它对正交约束提供的焦距
    # 信息越少。实测（6 种机位）：竖直 VP 在 35657px 时含它的对误差达 -8.1%，
    # 而 x/y 两 VP 恒在 500~1600px，f_xy **始终 ±0.2%**。
    # 故按定位质量排序取主对，而不是要求三对全都一致。
    diag = math.hypot(W, H)
    loc = {k: vp_localization(vps[k], cx, cy, diag) for k in AXES}
    pairs = {}
    for a, b in (("x", "y"), ("x", "z"), ("y", "z")):
        fv = focal_from_pair(vps[a], vps[b], cx, cy)
        if fv is None:
            continue
        pairs[f"{a}{b}"] = {"f": round(fv, 2),
                            "loc": round(max(loc[a], loc[b]), 2)}   # 越小越可信
    if not pairs:
        raise ValueError(
            "三对正交都解不出焦距 —— 消失点位形退化（典型成因：相机正对某个平面, "
            "该方向的线在图上仍平行）。"
        )
    best = min(pairs.values(), key=lambda v: v["loc"])
    if best["loc"] > VP_LOCALIZATION_LIMIT:
        raise ValueError(
            f"所有消失点都过于接近无穷远（最好的一对 loc={best['loc']}, 上限 "
            f"{VP_LOCALIZATION_LIMIT}）—— 该照片的透视太弱, 焦距不可信。"
        )
    # 只要求「可信度相当」的几对互相印证；把病态对拉进来比较毫无意义。
    comparable = {k: v for k, v in pairs.items() if v["loc"] <= 2 * best["loc"]}
    vals = [v["f"] for v in comparable.values()]
    spread = (max(vals) - min(vals)) / min(vals) * 100 if len(vals) > 1 else None
    if spread is not None and spread > F_CONSISTENCY_LIMIT_PCT:
        raise ValueError(
            f"可信度相当的几对正交解出的焦距互不印证（{comparable}, 差异 {spread:.1f}%）"
            f"—— 线的方向分组可能有误。"
        )
    fs = {k: v["f"] for k, v in pairs.items()}
    f = float(np.mean(vals))
    stable = comparable
    R = rotation_from_vps(vps, f, cx, cy)
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    return {
        "K": K, "R": R, "f": f,
        "vps": {k: (vps[k] / (np.linalg.norm(vps[k]) + 1e-12)).tolist() for k in AXES},
        "vp_stability_deg": {k: (None if stab[k] is None else round(stab[k], 3)) for k in AXES},
        "line_residual_deg": {k: [round(r, 3) for r in resids[k]] for k in AXES},
        "max_line_residual_deg": round(max(max(v) for v in resids.values()), 3),
        "f_per_pair": fs,
        "f_pair_detail": pairs,
        "vp_localization": {k: round(loc[k], 3) for k in AXES},
        "f_pairs_used": list(stable),
        "f_spread_pct": None if spread is None else round(spread, 2),
        "n_lines": {k: len(groups[k]) for k in AXES},
        # 自检成立 = 每轴 >=3 条线（逐条残差与留一稳定性才有意义）。
        # f 的跨对印证是**加分项**：真实室内照里竖直消失点通常很远，
        # 常常只有一对正交可信，那时无从跨对核对 —— 如实标注为 cross_checked=False。
        "self_checked": all(stab[k] is not None for k in AXES),
        "cross_checked": len(stable) >= 2,
        "det_R": round(float(np.linalg.det(R)), 6),
    }


def _angle(R1: np.ndarray, R2: np.ndarray) -> float:
    c = (np.trace(R1.T @ R2) - 1) / 2
    return float(math.degrees(math.acos(max(-1.0, min(1.0, c)))))


def angle_between_rotations_deg(R1: np.ndarray, R2: np.ndarray, *,
                                modulo_sign_ambiguity: bool = True) -> float:
    """两个姿态之间的夹角（度）—— 「自动 vs 人工」的 R 差距就用这个量。

    默认把**符号歧义商掉**（见 rotation_from_vps）：消失点定不了轴的指向，两条
    路线都受同一歧义影响，若不商掉，同一个姿态会被算成相差 180°。

    ⚠ 商掉歧义是为了让「自动 vs 人工」可比，**不等于歧义不存在**。产品要用这台
    相机出图时，符号必须被真正定下来（需 >=1 个锚点），否则 180° 翻转会让引导图
    彻底错位。这条限制须写进 go/no-go。传 modulo_sign_ambiguity=False 可量出
    未消歧时的真实差距。
    """
    if not modulo_sign_ambiguity:
        return _angle(R1, R2)
    return min(_angle(V, R2) for V in canonical_variants(R1))
