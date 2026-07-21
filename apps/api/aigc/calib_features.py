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

# calib-cure-b2 F002: 异面点高度 (破共面退化的关键——通用 PnP 有不同高度点才良态)。
# 墙-天花板角/落地窗顶用真实层高 perspective._REAL_CEILING_MM=2700 (最可信, 与既有约定同源)。
# openings 无高度字段 (geometry 仅含 wall/wtype), 门叶顶用标准室内门高常量 (近似, 已注明)。
_DOOR_HEAD_MM = 2050.0

# calib-cure-b3 F003: 特征供给稳健化 —— 按"这个点在现实照片里有没有清晰对应物"分级。
# 开工前调查实证: wtype 是**人工标注的几何数据**(编辑器 GeometrySidePanel 下拉可改 / golden
# 从 SVG data-wtype 解析), 不是从现场推导的 —— 故 wtype=='full' 只代表"图纸标为落地窗",
# 不保证现场真是落地窗。真实病例里窗常齐腰/带护栏, z=0 窗框地面交点在照片中根本无对应物,
# 用户被迫瞎点 -> 污染解算。**不改 data/projects (红线)**, 只在派生层下发分级, 由 UI 降级呈现。
#
# tier / priority (小=优先) / optional (可跳过, UI 明示) / caveat_zh (存疑说明, 无则 None):
#   structural(0) 墙角 z=0 + 天花板角 z=2700 —— 平面几何直出 + 层高为全局约定, 最可信;
#   opening(1)    门框竖边 z=0 精确; 门顶 z=2050 为标准门高近似 (带 caveat, 但仍必点);
#   uncertain(2)  窗地/窗顶 —— wtype 与真实窗型可能失配, 降级为辅助点, 明确可跳过。
_TIER_STRUCTURAL = "structural"
_TIER_OPENING = "opening"
_TIER_UNCERTAIN = "uncertain"

_WINDOW_FLOOR_CAVEAT = (
    "图纸标注为落地窗, 但现场若是齐腰窗 / 窗框带护栏(窗框不落到地面), "
    "照片里没有对应物 —— 找不到就跳过此特征, 优先点墙角与天花板转角"
)
_WINDOW_HEAD_CAVEAT = (
    "窗顶按『到顶(层高 2700)』推算, 现场窗顶更低时照片里对不上 —— "
    "对不上就跳过此特征, 优先点墙角与天花板转角"
)
_DOOR_HEAD_CAVEAT = "门顶高按标准室内门 2050mm 近似(geometry 无门高数据), 允许略有出入"

# kind -> (tier, priority, optional, caveat_zh)
_KIND_TIER: dict = {
    "wall_corner": (_TIER_STRUCTURAL, 0, False, None),
    "ceiling_corner": (_TIER_STRUCTURAL, 0, False, None),
    "door_jamb": (_TIER_OPENING, 1, False, None),
    "door_head": (_TIER_OPENING, 1, False, _DOOR_HEAD_CAVEAT),
    "window_floor": (_TIER_UNCERTAIN, 2, True, _WINDOW_FLOOR_CAVEAT),
    "window_head": (_TIER_UNCERTAIN, 2, True, _WINDOW_HEAD_CAVEAT),
}


def _member_labels(rooms_by_id: dict, members: list) -> tuple:
    """merge 组成员 -> (消歧后房名, 面积降序名次)。calib-cure-b3 F008（用户 L2 实测 FAIL）。

    病灶: 生产 m_living 三个成员 label.zh **全叫『客厅』**, 派生出『客厅·东南角』x3 等 8 组
    重名 —— UI 除小窗闪烁点外无区分手段, 用户被要求连点两个同名角, 误配几乎必然
    (实测 reproj 754px / 相机高 0.66m)。**不改 data(红线)**, 在派生层加方位后缀消歧。

    方位取成员形心相对组形心的主轴方向 (与小窗『上北下南』同约定); 同向撞车再退回序号。
    名次按成员面积降序 —— 让大房间的角先被轮候, 避免先点窄条房 (600x2800mm 的 r-itki-331
    四角是 PnP 最差基线, 却因 id 字母序恰好排最前, 实测把用户带进坑)。
    """
    info = []
    for mid in members:
        room = rooms_by_id.get(mid)
        if room is None:
            continue
        x, y, w, h = (float(v) for v in room["rect"])
        info.append({
            "id": mid,
            "zh": ((room.get("label") or {}).get("zh")) or mid,
            "cx": x + w / 2.0, "cy": y + h / 2.0, "area": w * h,
        })
    if not info:
        return {}, {}
    gx = sum(m["cx"] for m in info) / len(info)
    gy = sum(m["cy"] for m in info) / len(info)
    name_count: dict = {}
    for m in info:
        name_count[m["zh"]] = name_count.get(m["zh"], 0) + 1

    labels: dict = {}
    used: dict = {}
    for m in info:
        base = m["zh"]
        if name_count[base] == 1:
            labels[m["id"]] = base
            continue
        dx, dy = m["cx"] - gx, m["cy"] - gy
        if abs(dx) >= abs(dy):
            quad = "东" if dx > 0 else "西"
        else:
            quad = "南" if dy > 0 else "北"
        key = (base, quad)
        used[key] = used.get(key, 0) + 1
        # 同向撞车 -> 追加序号, 保证全局唯一 (宁可丑, 不可重名)
        suffix = quad if used[key] == 1 else f"{quad}{used[key]}"
        labels[m["id"]] = f"{base}({suffix})"

    ranks = {m["id"]: i for i, m in enumerate(sorted(info, key=lambda m: -m["area"]))}
    return labels, ranks


def _with_tier(feat: dict) -> dict:
    """按 kind 附置信度分级 (calib-cure-b3 F003)。未知 kind 保守归 opening, 不判存疑。"""
    tier, priority, optional, caveat = _KIND_TIER.get(
        feat.get("kind"), (_TIER_OPENING, 1, False, None)
    )
    return dict(
        feat,
        tier=tier,
        priority=priority,
        optional=optional,
        caveat_zh=caveat,
        # F008: 开口类不属任一成员房, 名次 0 (tier 已把它们与墙角分开, 组内不参与比较)。
        member_rank=int(feat.get("member_rank", 0)),
    )


def derive_features(G: dict, room_id: str) -> tuple[list[dict], list[str]]:
    """标定特征点池 -> (features, merge 成员 id 列表)。

    features: [{id, world:[x_mm,y_mm,z_mm], label_zh, kind, tier, priority, optional,
    caveat_zh}], id 稳定可复算 (binding/UI 引用)。
    kind (F002 后含异面点, z 可非 0):
      地面(z=0): wall_corner | door_jamb | window_floor;
      异面(z>0): ceiling_corner(z=2700) | door_head(z=2050) | window_head(z=2700)。
    异面点与对应地面点同 (x,y), 竖直配对给通用 PnP 破共面退化 (calib-cure-b2 F002)。
    tier/priority/optional/caveat_zh (calib-cure-b3 F003, 见 _KIND_TIER): 结构角最可信优先,
    窗特征因 wtype 与现场窗型可能失配而降级为可跳过辅助点 —— 消费端按 priority 排候选顺序。
    房间不存在时退回单成员 (同 render 侧容错)。
    """
    rooms_by_id = {str(r["id"]): r for r in G.get("rooms", []) if "id" in r}
    try:
        members = sorted(str(m) for m in axon.merge_group_ids(G, str(room_id)))
    except Exception:  # noqa: BLE001 - 房间已删/无 merge: 退回本房
        members = [str(room_id)]
    mm = float((G.get("meta", {}) or {}).get("mm_per_px", 10))
    # F008: 同组重名消歧 + 成员面积名次 (让大房间先轮候)。
    mem_labels, mem_ranks = _member_labels(rooms_by_id, members)
    feats: list[dict] = []

    # 1) 实体墙角: 跨成员重复坐标 = 开放边界虚拟角, 双方剔除。存活角同时出地面角(z=0)与
    #    天花板角(z=2700) —— 竖直配对给通用 PnP 异面约束 (F002)。天花板角与地面角同 (x,y)。
    seen: dict = {}
    for mid in members:
        room = rooms_by_id.get(mid)
        if room is None:
            continue
        x, y, w, h = room["rect"]
        label = mem_labels.get(mid) or ((room.get("label") or {}).get("zh")) or mid
        rank = mem_ranks.get(mid, 0)
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        for cname, (cx, cy) in zip(_CORNER_NAMES, corners):
            key = (round(float(cx), 1), round(float(cy), 1))
            wx, wy = float(cx) * mm, float(cy) * mm
            ground = {
                "id": f"corner:{mid}:{cname}",
                "world": [wx, wy, 0.0],
                "label_zh": f"{label}·{cname}角",
                "kind": "wall_corner",
                "member_rank": rank,
            }
            ceiling = {
                "id": f"ceilcorner:{mid}:{cname}",
                "world": [wx, wy, float(perspective._REAL_CEILING_MM)],
                "label_zh": f"{label}·{cname}顶角(天花板)",
                "kind": "ceiling_corner",
                "member_rank": rank,
            }
            seen.setdefault(key, []).append((ground, ceiling))
    for lst in seen.values():
        if len(lst) == 1:
            ground, ceiling = lst[0]
            feats.append(ground)
            feats.append(ceiling)

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
        # 每樘门/落地窗除地面交点(z=0)外, 追加框顶点(异面)——竖框上下配对给通用 PnP 竖直约束。
        if kind == "door":
            zh, fkind = "门框", "door_jamb"
            head_z, head_kind, head_prefix = _DOOR_HEAD_MM, "door_head", "doorhead"
        elif kind == "window" and op.get("wtype") == "full":
            zh, fkind = "落地窗框", "window_floor"
            head_z, head_kind, head_prefix = (
                float(perspective._REAL_CEILING_MM), "window_head", "winhead")
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
            wx, wy = float(jx) * mm, float(jy) * mm
            feats.append(
                {
                    "id": f"{kind}:{oid}:{suffix}",
                    "world": [wx, wy, 0.0],
                    "label_zh": f"{zh} {oid}·地面交点{suffix}",
                    "kind": fkind,
                }
            )
            feats.append(
                {
                    "id": f"{head_prefix}:{oid}:{suffix}",
                    "world": [wx, wy, head_z],
                    "label_zh": f"{zh} {oid}·顶点{suffix}",
                    "kind": head_kind,
                }
            )
    # F003: 附置信度分级 (tier/priority/optional/caveat_zh)。**排序契约仍是 id 字典序** ——
    # 稳定可复算、既有 binding/UI 引用零回归; 候选轮候顺序由消费端按 priority 排 (结构角优先),
    # 二者正交: 数据层给事实, 呈现层定顺序。
    return sorted((_with_tier(f_) for f_ in feats), key=lambda f_: f_["id"]), members


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


def _solve_pnp_coplanar(points: list, *, img_wh: tuple) -> "perspective.Camera":
    """全地面 (z≈0) 共面输入 -> Camera (既有单应分解路径, 逐字保留)。

    焦距扫描逐档分解评分 (评分 = 正交化后姿态的最大重投影残差, 对错误焦距敏感), 物理门
    (相机在地上 + 点在相机前) 过滤符号歧义。合成真值往返 <2px (单测钉住); 粗差输入表现为
    大残差, 由上层 assess 硬门拦截 —— 本函数只拒绝完全无解的退化输入。
    """
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


# ---- 通用 PnP (异面点; 已知 K 位姿 DLT + Gauss-Newton 精修) calib-cure-b2 F003 -----
# 异面点 (地面 z=0 + 天花板 z=2700 + 门窗顶) 破共面单应的退化 —— 真实斜拍照可见地面点又少
# 又近共线, 共面路径退化 (spike 报告 §1.2); 不同高度点让位姿良态, 精修把点击噪声平均掉。


def _pose_known_K(world3: np.ndarray, px: np.ndarray, K: np.ndarray):
    """已知 K, 从 ≥4 (异面更佳) 3D-2D 对解 [R|t] (归一化 DLT + 正交化)。

    产出两个整体符号候选; 物理门在调用处筛。正交化用 SVD 取最近正交阵 (不强加 det 号,
    让数据定手性), 与左手世界 det(R)=-1 约定自洽。
    """
    Kinv = np.linalg.inv(K)
    n = len(world3)
    Xh = np.c_[world3, np.ones(n)]
    xn = (Kinv @ np.c_[px, np.ones(n)].T).T
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
        yield U @ Vt2, t_raw / S.mean()


def _project3(f, R, t, cx, cy, world3):
    cam = R @ world3.T + t.reshape(3, 1)
    depth = cam[2]
    return np.column_stack([f * cam[0] / depth + cx, f * cam[1] / depth + cy]), depth


def _rodrigues(rvec: np.ndarray) -> np.ndarray:
    """旋转向量 -> 旋转矩阵 (det=+1); base_R 承载左手手性, rvec 只表增量。"""
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * Kx + (1 - np.cos(theta)) * (Kx @ Kx)


def _refine(f0, R0, t0, cx, cy, world3, px, iters=30):
    """非线性精修: 对 (f, 旋转增量, t) 最小化总重投影 (Gauss-Newton + LM 阻尼, 数值雅可比)。"""
    p = np.zeros(7)
    base_f, base_R, base_t = f0, R0.copy(), t0.copy()

    def resid(p):
        if abs(p[0]) > 2.0:  # log_f 钳制, 防退化初值下焦距爆
            return None
        f = base_f * np.exp(p[0])
        proj, depth = _project3(f, base_R @ _rodrigues(p[1:4]), base_t + p[4:7], cx, cy, world3)
        if np.any(depth <= 1e-6) or not np.all(np.isfinite(proj)):
            return None
        return (proj - px).reshape(-1)

    r = resid(p)
    if r is None:
        return f0, R0, t0
    lam, cost = 1e-3, float(r @ r)
    for _ in range(iters):
        J = np.zeros((len(r), 7))
        ok = True
        for j in range(7):
            dp = p.copy()
            dp[j] += 1e-6
            rj = resid(dp)
            if rj is None:
                ok = False
                break
            J[:, j] = (rj - r) / 1e-6
        if not ok:
            break
        H, g = J.T @ J, J.T @ r
        for _ls in range(8):
            try:
                step = np.linalg.solve(H + lam * np.eye(7), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            rn = resid(p + step)
            if rn is not None and float(rn @ rn) < cost:
                p, r, cost = p + step, rn, float(rn @ rn)
                lam = max(lam * 0.5, 1e-9)
                break
            lam *= 10
        else:
            break
    return base_f * np.exp(p[0]), base_R @ _rodrigues(p[1:4]), base_t + p[4:7]


def _solve_pnp_general(points: list, *, img_wh: tuple) -> "perspective.Camera":
    """异面点通用 PnP + GN 精修。焦距扫描定初值 (已知 K 位姿 DLT + 物理门 + 最小重投影),
    再 Gauss-Newton 精修全点。只拒绝完全无物理解的退化输入 (粗差由上层 assess 硬门拦)。"""
    world3 = np.array([[float(w[0]), float(w[1]), float(w[2])] for w, _p in points], float)
    px = np.array([[float(p[0]), float(p[1])] for _w, p in points], float)
    W, H_img = float(img_wh[0]), float(img_wh[1])
    cx, cy = W / 2.0, H_img / 2.0
    lo, hi, n = _HFOV_SCAN_DEG
    best = None
    for hfov in np.linspace(lo, hi, int(n)):
        f = (W / 2.0) / np.tan(np.radians(hfov) / 2.0)
        K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
        for R, t in _pose_known_K(world3, px, K):
            if float((-R.T @ t)[2]) <= 0:  # 相机在地板上方
                continue
            proj, depth = _project3(f, R, t, cx, cy, world3)
            if np.any(depth <= 1e-6):  # 点在相机前方
                continue
            err = float(np.max(np.hypot(*(proj - px).T)))
            if best is None or err < best[0]:
                best = (err, f, R, t)
    if best is None:
        raise ValueError("无物理有效的相机姿态解 (特征点世界/像素对应可能有误)")
    _, f, R, t = best
    f, R, t = _refine(f, R, t, cx, cy, world3, px)
    return perspective.Camera(
        K=np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]]), R=R, t=np.asarray(t, float)
    )


def solve_pnp(points: list, *, img_wh: tuple) -> "perspective.Camera":
    """≥4 特征点对 [((x,y,z),(u,v)), ...] -> Camera (共面或异面, calib-cure-b2 F003)。

    异面 (点跨多高度, 如地面+天花板) -> 通用 PnP + GN 精修 (破共面退化, 真实照片主路径);
    全地面 (z≈0) -> 既有共面单应路径 (逐字保留, 传统输入与既有单测零回归)。
    """
    if len(points) < 4:
        raise ValueError("solve_pnp 需 ≥4 个特征点")
    if max(abs(float(w[2])) for w, _p in points) <= 1.0:
        return _solve_pnp_coplanar(points, img_wh=img_wh)  # 全 z≈0: 既有路径
    return _solve_pnp_general(points, img_wh=img_wh)


# calib-cure-b3 F001 修复 (verifying-1): 共面判据 + 拍摄级引导文案。**不单独构成拦截** ——
# 必须与「解出的相机极端」合取后才成立 (acceptance 原文: 共面 *结合* 相机高度/hfov 极端)。
# 纯几何单边判据的实证代价: 8.7% 真良态选点被误拦 (解出相机高 1370-1446mm / hfov 70-72°,
# 完全健康), 而文案是「请重拍这张照片」—— 正是 F001 立项要消除的白跑。
_COPLANAR_S3_S1_MAX = 0.08

FACING_WALL_GUIDANCE = (
    "所选点几乎都在同一面墙上(共面), 且解出的相机不合理 — 正对一面墙拍的照片标不出来。"
    "请站到房间角落, 让画面同时带到两面相邻墙 + 地面墙角和天花板转角, 再重拍这张照片。"
)


def is_coplanar_across_heights(worlds: list) -> bool:
    """点跨了高度但整体近共面 (= 都贴同一面墙, 正对墙拍的几何签名)。

    只回答几何问题, **不做拦截判定** —— 调用方须与相机极端合取 (见 FACING_WALL_GUIDANCE)。
    """
    if len(worlds) < 4:
        return False
    P = np.array([[float(w[0]), float(w[1]), float(w[2])] for w in worlds], float)
    s = np.linalg.svd(P - P.mean(axis=0), compute_uv=False)
    if s[0] < 1e-9:
        return False
    return bool(float(np.ptp(P[:, 2])) > 1.0 and s[2] / s[0] < _COPLANAR_S3_S1_MAX)


def degeneracy_reason(worlds: list):
    """点位退化预检 -> 可行动中文提示 (无退化返回 None)。解算前调用, 比 solve 后高 reproj
    更明确。**保守**: 只拦明显退化; 边际情形交给 assess reproj 门 (真安全网)。阈值取自 spike
    (solver.degeneracy 的奇异值比)。识别两类退化 (均给拍摄级可行动提示, 门不放宽):
      - 近共线 (s2/s1<0.12): 点几乎一条线 (b2 F004; spike r_study≈0 死局);
      - 全同高地面且 XY 近共线 (b2 F004): 提示补天花板/异面点。

    **「正对墙/共面」不在此处** (calib-cure-b3 F001, verifying-1 修复): 纯几何单边判据实证
    误拦 8.7% 真良态选点 —— 共面本身不致命 (平面目标可由单应解出健康相机), 致命的是
    「共面 AND 解出的相机极端」。该合取需要解算后的相机, 故挂在 assess 层, 见
    is_coplanar_across_heights / FACING_WALL_GUIDANCE 与 main._facing_wall_reason。
    """
    if len(worlds) < 4:
        return None  # 点数由上层 ≥4 校验管
    P = np.array([[float(w[0]), float(w[1]), float(w[2])] for w in worlds], float)
    s = np.linalg.svd(P - P.mean(axis=0), compute_uv=False)
    if s[0] < 1e-6:
        return "所选特征点几乎重合 — 请点相距更远、在画面里铺开的特征"
    if s[1] / s[0] < 0.12:  # 3D 第二主轴塌缩 = 近共线, 任何 PnP 都退化 (spike: r_study≈0 死局)
        return "所选特征点几乎共线(都在一条直线上) — 请点到不同墙面, 让点在画面里铺开"
    # calib-cure-b3 F010 (用户 L2-3 实测): **平面位置少于 3 个** = 所有点挤在同一面墙的两条
    # 竖线上 (如 东北角/东南角 + 各自天花板孪生), 俯视看只有两个点。这是比「共面」更窄、更
    # 确定的死局判据: 实测在 115 组真良态选点上**误伤 0 组 (0.0%)**, 而「共面」判据误伤 8.7%
    # (F001 就栽在后者)。故此条可安全地在**解算前**拦 —— 早拦省得用户点满 4 点后收到一句
    # 指错方向的「你把左右点反了」(该镜像判定在退化位形下本就不可信, 见 main._facing_wall_reason)。
    xy = {(round(float(w[0]), 1), round(float(w[1]), 1)) for w in worlds}
    if len(xy) < 3:
        return (
            f"所选点在平面上只落在 {len(xy)} 个位置(都在同一面墙上) — 这样解不出相机。"
            "请再点一个其他墙面上的角(与现有点不在同一面墙), 让点在俯视平面上铺开成三角形; "
            "天花板角与它正下方的地面角算同一个位置, 不能替代。"
        )
    # F001 的「正对墙/共面」判据**不在此处拦截** —— 见 coplanar_ratio 与 FACING_WALL_GUIDANCE:
    # verifying-1 实证纯几何判据会误拦 8.7% 的真良态选点(解出的相机完全健康), 把用户赶去重拍
    # 一张本来没问题的照片。acceptance 原文要求的是「共面 **结合** 相机高度/hfov 极端」的合取,
    # 合取需要解算后的相机, 故该诊断改挂 assess 层 (acceptance 已许可)。
    if float(np.ptp(P[:, 2])) <= 1.0:  # 全同高 (共面地面): XY 需铺开, 否则提示补异面点
        sxy = np.linalg.svd(P[:, :2] - P[:, :2].mean(axis=0), compute_uv=False)
        if sxy[0] > 1e-6 and sxy[1] / sxy[0] < 0.30:
            return (
                "所选点都在地面且接近一条线 — 请再点一个天花板转角(或不同墙的角), "
                "把点铺到不同高度"
            )
    return None
