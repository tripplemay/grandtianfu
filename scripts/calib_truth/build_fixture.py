#!/usr/bin/env python3
"""calib-route-a1 F001 — 由人工对应构建真值夹具（含留一法不确定度）。

用法:
    # 1) 列出某房间的候选世界点（喂给标注工具 mark.html）
    python3 scripts/calib_truth/build_fixture.py points \\
        --geometry <path>/geometry.json --room r_master

    # 2) 由标注导出的对应构建夹具
    python3 scripts/calib_truth/build_fixture.py build \\
        --geometry <path>/geometry.json --room r_master \\
        --photo <path>/xxx.jpg --marks marks.json \\
        --out docs/../fixtures/r_master.json

**PIPL 铁律：输出只含数值** —— 相机参数、对应坐标、照片 sha256 与宽高。
照片像素、文件名、路径一律不写入夹具，夹具可安全入 git。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import solve as S            # noqa: E402
import solve_plane as SP     # noqa: E402
import world_points as WP    # noqa: E402

# 留一法不确定度的可用阈值（px）。超过即判「该照片不适合当真值」——
# spec §D1 明令：不得为凑数把不可信的当真值。
UNCERTAINTY_LIMIT_PX = 12.0

# 两种真值模式的最小标注数：
#   plane（默认）—— 只用地面点。单应需 4 点，留一后仍须 4 => 至少 5。
#   full        —— 混合高度点，依赖层高/门头等**假设坐标**。DLT 需 6，留一 => 至少 7；
#                  spec §D1 原定 10 以留冗余。
MIN_MARKS = {"plane": 5, "full": 10}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_points(args) -> int:
    G = json.loads(Path(args.geometry).read_text())
    pts = WP.floor_candidates(G, args.room) if args.mode == "plane" \
        else WP.candidates(G, args.room)
    if not pts:
        print(f"房间 {args.room} 无候选点（检查 room id）", file=sys.stderr)
        return 2
    out = {
        "room_id": args.room,
        "mode": args.mode,
        # plane 模式下点必然共面, 那是设计而非缺陷, 故不报 coplanar 警告
        "coplanar_warning": (args.mode == "full" and not WP.non_coplanar(pts)),
        "min_marks": MIN_MARKS[args.mode],
        "points": [{"id": p.id, "xyz": list(p.xyz), "label": p.label, "kind": p.kind}
                   for p in pts],
    }
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(txt)
        print(f"{len(pts)} 个候选点 -> {args.out}")
    else:
        print(txt)
    return 0


def _load_marks(G: dict, room: str, marks_path: Path) -> list[S.Corr]:
    """标注文件 -> 对应列表。marks: [{"point_id": ..., "px": [u, v]}, ...]

    按全量候选查表（不按模式过滤），这样 plane 模式下若混入了非地面点，
    会在下面的 z 检查里**明确报错**，而不是被静默丢弃。
    """
    by_id = {p.id: p for p in WP.candidates(G, room)}
    marks = json.loads(marks_path.read_text())
    if isinstance(marks, dict):
        marks = marks.get("marks", [])
    corr: list[S.Corr] = []
    unknown = []
    for m in marks:
        p = by_id.get(m["point_id"])
        if p is None:
            unknown.append(m["point_id"])
            continue
        corr.append((tuple(p.xyz), (float(m["px"][0]), float(m["px"][1]))))
    if unknown:
        raise SystemExit(f"标注引用了不存在的候选点: {unknown}")
    return corr


def cmd_build(args) -> int:
    G = json.loads(Path(args.geometry).read_text())
    photo = Path(args.photo)
    corr = _load_marks(G, args.room, Path(args.marks))
    need = MIN_MARKS[args.mode]

    if len(corr) < need:
        print(f"✗ 只有 {len(corr)} 个对应，{args.mode} 模式需 >= {need}。"
              f"\n  请补标；若这张照片凑不够可指认的点，说明它不适合当真值 —— 换一张。",
              file=sys.stderr)
        return 2

    W = np.array([c[0] for c in corr], float)

    try:
        from PIL import Image
        with Image.open(photo) as im:
            img_wh = list(im.size)
    except Exception:  # noqa: BLE001 - 夹具不该因读不到图就失败
        img_wh = None

    info: dict = {}
    if args.mode == "plane":
        if not np.allclose(W[:, 2], 0.0):
            bad = sorted({float(z) for z in W[:, 2] if z != 0.0})
            print(f"✗ plane 模式只接受地面点（z=0），但标注里含 z={bad}。"
                  f"\n  这些点的高度是**假设值**（层高/门头常量），不可入真值。", file=sys.stderr)
            return 2
        if img_wh is None:
            print("✗ plane 模式需要图像宽高来定主点，但读不到照片。", file=sys.stderr)
            return 2
        try:
            K, R, t, info = SP.solve_camera_plane(corr, tuple(img_wh))
            loo = SP.leave_one_out_plane(corr, tuple(img_wh))
        except ValueError as e:
            print(f"✗ 单平面标定失败：{e}", file=sys.stderr)
            return 2
    else:
        if np.linalg.matrix_rank(W - W.mean(0), tol=1e-6) < 3:
            print("✗ 所标点全部共面 —— 通用 DLT 退化。"
                  "\n  请补入不同高度的点，或改用 --mode plane（单平面标定，共面正是它要的）。",
                  file=sys.stderr)
            return 2
        K, R, t = S.solve_camera(corr)
        loo = S.leave_one_out(corr)

    fit = S.reproj_errors(K, R, t, corr)
    center = (-R.T @ t).tolist()
    usable = loo["median_px"] <= UNCERTAINTY_LIMIT_PX
    if args.mode == "plane" and not info.get("self_consistent", True):
        usable = False
    fixture = {
        "schema": "calib_truth/v1",
        "mode": args.mode,
        "room_id": args.room,
        "photo": {"sha256": sha256_of(photo), "wh": img_wh},   # 无文件名/路径（PIPL）
        "camera": {
            "K": K.tolist(), "R": R.tolist(), "t": t.tolist(),
            "center_mm": center,
            "det_R": round(float(np.linalg.det(R)), 6),
            "f_px": round(float((K[0, 0] + K[1, 1]) / 2), 2),
        },
        "correspondences": [{"xyz": list(w), "px": list(p)} for w, p in corr],
        "fit": {
            "median_px": round(float(np.median(fit)), 2),
            "max_px": round(float(fit.max()), 2),
        },
        "uncertainty": loo,
        "self_check": info,
        "usable_as_truth": bool(usable),
        "notes": [
            "留一法留出误差 = 本真值的不确定度；拟合误差(fit)仅供对照，不得当作精度。",
            f"判定阈值 {UNCERTAINTY_LIMIT_PX}px（中位留出误差）。",
            "det_R 在本仓左手世界系(X东/Y南/Z上)下应为 -1；见 solve.py 抬头说明。",
            ("plane 模式：世界坐标零假设（x/y 来自平面图，z=0 是地面定义）；"
             "另需两路 f 估计互相印证（self_check.self_consistent）。"
             if args.mode == "plane" else
             "full 模式：天花 2700 / 门头 2050 是**假设值**，真值精度受其牵连。"),
        ],
    }

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(fixture, ensure_ascii=False, indent=1))

    print(f"[{args.mode}] 对应 {len(corr)} 个 | 拟合中位 {fixture['fit']['median_px']}px | "
          f"留出中位 {loo['median_px']}px (max {loo['max_px']}px)")
    print(f"相机 f={fixture['camera']['f_px']}px  中心={[round(v) for v in center]}mm  "
          f"det(R)={fixture['camera']['det_R']}")
    if info:
        for r in info["routes"]:
            print(f"自检 route{r['route']}: f={r['f']} 留一CV={r['cv_pct']}% "
                  f"-> {'可信' if r['stable'] else '不稳(弃用)'}")
        print(f"     {info['n_stable']}/2 路可信"
              + (f"，交叉印证差异 {info['f_spread_pct']}%" if info["cross_checked"]
                 else "，**只有一路可信，无冗余可交叉核对**"))
    if center[2] <= 0:
        print("⚠ 相机中心在地板下方 —— 该解物理无效，不可当真值。", file=sys.stderr)
        return 2
    if not usable:
        print(f"✗ 留出误差中位 {loo['median_px']}px > {UNCERTAINTY_LIMIT_PX}px 阈值。"
              f"\n  按 spec §D1：这张照片**不适合当真值**，请换一张，"
              f"不得为凑数把不可信的当真值。", file=sys.stderr)
        return 1
    print("✓ 可用作真值")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_mode(p):
        p.add_argument("--mode", choices=("plane", "full"), default="plane",
                       help="plane(默认)=仅地面点, 坐标零假设; full=混合高度, 依赖层高等假设值")

    p1 = sub.add_parser("points", help="列出房间的候选世界点")
    p1.add_argument("--geometry", required=True)
    p1.add_argument("--room", required=True)
    p1.add_argument("--out")
    add_mode(p1)
    p1.set_defaults(fn=cmd_points)

    p2 = sub.add_parser("build", help="由标注构建真值夹具")
    p2.add_argument("--geometry", required=True)
    p2.add_argument("--room", required=True)
    p2.add_argument("--photo", required=True)
    p2.add_argument("--marks", required=True)
    p2.add_argument("--out")
    add_mode(p2)
    p2.set_defaults(fn=cmd_build)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
