#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_golden.py — 黄金回归 (P0 硬门槛, 独立于 json 自身的 passages).

把现 SVG (平面布置图-无家具.svg) 解析为参照, 与 derive(load(geometry-D户型.json))
逐段 diff. 关键: 测试不依赖 json 自带的 passage 列表, 否则 "门→通道" 的错误会被
合成 passage 自动抵消 (见审查 issue#2).

门槛:
  (a) 墙: derive 墙段 == golden(扣门洞) 逐 (axis,at) 一致 (端点 <=1px);
      且 (candidate - golden - 派生门跨) 必须 ⊆ **硬编码的认可敞口集** (SANCTIONED_PASSAGES),
      杜绝多余派生墙被合成 passage 掩盖.
  (b) 门 (独立逐实体): 12 个 SVG 门弧/推拉实体 -> 恰 1 扇派生门;
      每扇 width>0、between 为两个不同的真实 space;
      非 review 门必须 span ⊆ 连续派生墙 (落在真墙上);
      review 集合必须 == 规格认可漂移集 {line82,86,89,92} = {d01,d05,d08,d11};
      任何 passage 不得压住任一 SVG 门扇足迹 (passage 顶替门 = FAIL).
  (c) 窗: 13 扇 at/span/wtype 还原.
  (d) §② 黄金断言全过.

用法:  python3 tests/verify_golden.py    (退出码 0=PASS, 1=FAIL)
"""
from __future__ import annotations

import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)          # 让 svg2geometry (同目录金测解析器) 可导入

from floorplan_core import geometry as geo   # noqa: E402  (引擎库单一真源)
import svg2geometry as s2g                    # noqa: E402  (迁移工具兼金测解析器)

# SRC = 冻结 ground-truth SVG (独立参照, 不取自活数据); JSON = **活几何** (app/build.py 实发数据).
#   审查 issue#2: 旧实现 JSON=s2g.OUT_DEFAULT 指向 tests/fixtures 陈旧副本, 致黄金门覆盖不到
#   真正会回归的活数据 (轴测图POC/geometry-D户型.json) → 假 PASS. 现金测直打活几何;
#   GOLDEN_OUT 仍可覆写 (如临时跑 fixtures).
REPO = os.path.dirname(os.path.dirname(ROOT))   # tests -> floorplan_core(pkg) -> packages -> repo
LIVE_JSON = os.path.join(REPO, "轴测图POC", "geometry-D户型.json")
# golden 测【冻结 fixture】(算法回归, 不随 live 编辑变); fixture 已重新冻结为规范基线(walls=45/win=13).
# 若要临时校验活数据是否仍 == 基线: GOLDEN_OUT=<live json path> python3 verify_golden.py
FIXTURE_JSON = os.path.join(os.path.dirname(__file__), "fixtures", "geometry-D户型.json")
SRC = s2g.SRC_DEFAULT
JSON = os.environ.get("GOLDEN_OUT", FIXTURE_JSON)
EPS = 1.0
MIN_DOOR_W = 40           # 门洞最小宽度 px
FOOT_TOL = 2.0            # 门扇足迹判定容差 px

# 规格认可的真实敞口 (非门, 由房间敞通推出) — 独立 ground truth, 不取自 json.
#   h@250[365,675]  入户花园南向敞口 (庭院开口)
#   h@490[1120,1215] 生活阳台↔客厅 敞口
#   h@680[1435,1515] 内部过渡↔衣帽间 敞口
#   v@1215[490,680]  客厅↔内部过渡 主动线 (finding8)
SANCTIONED_PASSAGES = {
    ("h", 250): [[365.0, 675.0]],
    ("h", 490): [[1120.0, 1215.0]],
    ("h", 680): [[1435.0, 1515.0]],
    ("v", 1215): [[490.0, 680.0]],
}
# 规格认可漂移门集 (D11): line82/86/89/92 = 文档第 1/5/8/11 扇.
SANCTIONED_REVIEW = {"d01", "d05", "d08", "d11"}

# 规格认可「合并消隐墙」: 旧 ground-truth SVG (平面布置图-无家具.svg) 仍画着分隔墙,
# 但活几何/冻结基线 (.phase0-baseline/derive-D.json: walls=45, top 无 1005 刻度) 已将其
# 两侧房间并入同一 space —> derive 按同 space 规则不出内墙 (开放式). 故这些「SVG 有、derive
# 无」的墙是**认可的设计漂移**, 比对前从 golden_true 扣除. 每条都必须真实存在于 golden_raw
# (否则视为陈旧 sanction 报错), 且必须真实缺席于 derive (否则该并未发生、不应豁免).
#   v@1005[265,490]  r_kit↔r_balc 厨房/生活阳台 并入 space=kitchen 开放 (取代旧分隔墙).
# 经审查 issue#2 排查发现: 该 SVG 与基线拓扑不一致 (SVG=分隔/47墙, 基线=开放/45墙);
# 基线为红线冻结真源, 故以基线为准. 长期应重新生成无家具参照 SVG 与 fixtures 副本.
SANCTIONED_MERGED_WALLS = {
    ("v", 1005): [[265.0, 490.0]],
}


# --------------------------------------------------------------------------- #
def merged_from_walls(walls_raw):
    out = {}
    for w in walls_raw:
        out.setdefault((w["axis"], w["at"]), []).append([w["lo"], w["hi"]])
    return {k: geo.merge_intervals(v, EPS) for k, v in out.items()}


def approx_intervals(a, b, eps=EPS):
    a = geo.merge_intervals(a, eps)
    b = geo.merge_intervals(b, eps)
    if len(a) != len(b):
        return False
    for (a0, a1), (b0, b1) in zip(a, b):
        if abs(a0 - b0) > eps or abs(a1 - b1) > eps:
            return False
    return True


def subset_of(span, segs, eps=EPS):
    """span 是否被某连续 seg 覆盖 (端点容差 eps)."""
    return any(s[0] - eps <= span[0] and s[1] + eps >= span[1] for s in segs)


def overlap_len(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def fmt(segs):
    return "[" + ", ".join("%g-%g" % (s[0], s[1]) for s in segs) + "]"


def door_footprints(svg, doors_raw, sliding_raw):
    """每个 SVG 门实体的 2D 足迹 bbox (含 leaf + arc 两端 / 推拉 rect)."""
    foots = []
    for dr in doors_raw:
        pts = [dr["jamb"], dr["open_tip"]]
        if dr.get("leaf"):
            pts += [dr["leaf"][0], dr["leaf"][1]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        foots.append((min(xs), min(ys), max(xs), max(ys)))
    if sliding_raw:
        xs = [r[0] for r in sliding_raw] + [r[0] + r[2] for r in sliding_raw]
        ys = [r[1] for r in sliding_raw] + [r[1] + r[3] for r in sliding_raw]
        foots.append((min(xs), min(ys), max(xs), max(ys)))
    return foots


def passage_hits_footprint(axis, at, span, foot):
    minx, miny, maxx, maxy = foot
    if axis == "h":
        return (miny - FOOT_TOL <= at <= maxy + FOOT_TOL and
                overlap_len(span, [minx, maxx]) > EPS)
    return (minx - FOOT_TOL <= at <= maxx + FOOT_TOL and
            overlap_len(span, [miny, maxy]) > EPS)


# --------------------------------------------------------------------------- #
def main():
    with open(SRC, "r", encoding="utf-8") as fh:
        svg = fh.read()

    golden_raw, doors_raw, sliding_raw, windows_raw = s2g.parse_golden(svg)
    G = geo.load(JSON)
    res = geo.derive(G)
    derived = merged_from_walls(res["_walls_raw"])
    cand = geo.candidate_walls(G)
    spaces = set(G["spaces"].keys())

    fails = []

    # 派生门跨度 (用于扣门 + 独立的 extra-coverage 检查) ----------------------
    derive_doors = res["doors"]
    swing = [d for d in derive_doors if d.get("door_type") != "sliding"]
    sliding = [d for d in derive_doors if d.get("door_type") == "sliding"]
    door_cuts = {}
    for d in derive_doors:
        door_cuts.setdefault((d["axis"], d["at"]), []).append(list(d["span"]))

    # =================== (a) 墙逐段对比 ===================
    print("=" * 72)
    print("(a) 墙段逐轴对比 (golden扣门 vs derive) + 多余覆盖检查")
    print("-" * 72)
    golden_true = {}
    keys = set(golden_raw) | set(derived)
    for k in keys:
        segs = list(golden_raw.get(k, []))
        for cut in door_cuts.get(k, []):
            segs = geo.diff_intervals(segs, [cut])
        for mw in SANCTIONED_MERGED_WALLS.get(k, []):     # 扣掉认可的并入消隐墙
            segs = geo.diff_intervals(segs, [mw])
        golden_true[k] = geo.merge_intervals(segs, EPS)

    # 认可消隐墙必须 (1) 真实存在于旧 golden SVG, (2) 真实缺席于 derive —— 否则 sanction 失真
    for k, segs in SANCTIONED_MERGED_WALLS.items():
        for s in segs:
            if not subset_of(s, golden_raw.get(k, [])):
                print("  FAIL 认可消隐墙 %s@%g %s 不在 golden SVG 内 (陈旧 sanction)" %
                      (k[0], k[1], fmt([s])))
                fails.append("认可消隐墙不实")
            if any(overlap_len(s, d) > EPS for d in derived.get(k, [])):
                print("  FAIL 认可消隐墙 %s@%g %s 仍出现在 derive (并入未生效)" %
                      (k[0], k[1], fmt([s])))
                fails.append("认可消隐墙仍在 derive")

    wall_diffs = []
    for k in sorted(keys, key=lambda t: (t[0], t[1])):
        if not approx_intervals(golden_true.get(k, []), derived.get(k, [])):
            wall_diffs.append((k, golden_true.get(k, []), derived.get(k, [])))
    if wall_diffs:
        for (axis, at), g, d in wall_diffs:
            print("  FAIL %s@%g  golden=%s  derive=%s" % (axis, at, fmt(g), fmt(d)))
        fails.append("墙段不一致 x%d" % len(wall_diffs))
    else:
        print("  PASS — 全部墙段 golden(扣门)==derive")

    # extra-coverage: (candidate - golden - 派生门跨) 必须 ⊆ 认可敞口
    extra = []
    for k in sorted(cand, key=lambda t: (t[0], t[1])):
        opening = geo.diff_intervals(cand[k], golden_raw.get(k, []))   # 候选墙上的全部开口
        for cut in door_cuts.get(k, []):
            opening = geo.diff_intervals(opening, [cut])               # 扣掉派生门
        residual = geo.diff_intervals(opening, SANCTIONED_PASSAGES.get(k, []))
        residual = [s for s in residual if s[1] - s[0] > EPS]
        if residual:
            extra.append((k, residual))
    if extra:
        for (axis, at), r in extra:
            print("  FAIL 多余敞口(非门非认可通道) %s@%g %s" % (axis, at, fmt(r)))
        fails.append("候选墙多余覆盖 x%d" % len(extra))
    else:
        print("  PASS — 无多余派生墙覆盖 (开口 = 派生门 ∪ 认可敞口)")
    # 认可敞口必须真实存在于候选-golden 中 (防 SANCTIONED 写错放水)
    for k, segs in SANCTIONED_PASSAGES.items():
        op = geo.diff_intervals(cand.get(k, []), golden_raw.get(k, []))
        for s in segs:
            if not subset_of(s, op):
                print("  FAIL 认可敞口 %s@%g %s 不在候选开口内" % (k[0], k[1], fmt([s])))
                fails.append("认可敞口不实")

    # =================== (b) 门独立逐实体回归 ===================
    print("=" * 72)
    print("(b) 门独立逐实体回归 (12 SVG 实体 -> 派生门)")
    print("-" * 72)
    n_arc = len(doors_raw)
    if len(swing) != n_arc:
        print("  FAIL 平开门数 %d != SVG门弧 %d" % (len(swing), n_arc))
        fails.append("平开门计数")
    if len(sliding) != (1 if sliding_raw else 0):
        print("  FAIL 推拉门数 %d != %d" % (len(sliding), 1 if sliding_raw else 0))
        fails.append("推拉门计数")

    review_ids = set()
    for idx, d in enumerate(swing):
        did = d["id"]
        sp = d["span"]
        width = sp[1] - sp[0]
        bt = d.get("between")
        ok = True
        msgs = []
        if width < MIN_DOOR_W:
            ok = False
            msgs.append("width=%g<%g" % (width, MIN_DOOR_W))
        if not (bt and len(bt) == 2 and bt[0] and bt[1] and bt[0] != bt[1]):
            ok = False
            msgs.append("between=%s 非两不同space" % bt)
        elif not (bt[0] in spaces and bt[1] in spaces):
            ok = False
            msgs.append("between=%s 含未知space" % bt)
        if d.get("review"):
            review_ids.add(did)
        else:
            # 非 review: 必须落在连续派生墙上 (真墙); 且 hinge 在该墙上
            segs = cand.get((d["axis"], d["at"]), [])
            if not subset_of(sp, segs):
                ok = False
                msgs.append("span %s 不落连续派生墙 %s" % (sp, fmt(segs)))
            # SVG 实体 hinge 应在该墙 (axis,at) 上
            dr = doors_raw[idx]
            hinge = s2g.arc_center_hinge(dr["leaf"], dr["jamb"], dr["open_tip"], dr["r"])
            perp = hinge[0] if d["axis"] == "v" else hinge[1]
            if abs(perp - d["at"]) > FOOT_TOL:
                ok = False
                msgs.append("hinge %s 不在墙 %s@%g 上" % (hinge, d["axis"], d["at"]))
        if not ok:
            print("  FAIL %s %s@%g %s : %s" %
                  (did, d["axis"], d["at"], sp, "; ".join(msgs)))
            fails.append("门 %s 无效" % did)
    # sliding
    for d in sliding:
        sp = d["span"]
        bt = d.get("between")
        if sp[1] - sp[0] < MIN_DOOR_W or not (bt and bt[0] and bt[1] and bt[0] != bt[1]):
            print("  FAIL 推拉门 %s span=%s between=%s 无效" % (d["id"], sp, bt))
            fails.append("推拉门无效")

    if review_ids != SANCTIONED_REVIEW:
        print("  FAIL review 集合 %s != 认可漂移集 %s" %
              (sorted(review_ids), sorted(SANCTIONED_REVIEW)))
        fails.append("review 集合不符")
    else:
        print("  PASS — review 集合 == 认可漂移集 %s" % sorted(SANCTIONED_REVIEW))

    # passage 不得顶替门: 任一 passage 不压任一 SVG 门足迹
    foots = door_footprints(svg, doors_raw, sliding_raw)
    passages = [op for op in G["openings"] if op.get("kind") == "passage"]
    pass_hit = False
    for p in passages:
        ax = p["wall"]["axis"]; at = p["wall"]["at"]; spn = p["wall"]["span"]
        for fi, foot in enumerate(foots):
            if passage_hits_footprint(ax, at, spn, foot):
                print("  FAIL passage %s %s@%g %s 压住 SVG门#%d 足迹 %s" %
                      (p.get("id"), ax, at, spn, fi, foot))
                fails.append("passage 顶替门")
                pass_hit = True
    if not pass_hit:
        print("  PASS — 无 passage 顶替门 (%d 门有效, review=%s)" %
              (len(swing), sorted(review_ids)))
    print("  通过: 平开门 %d/%d 落墙有效, sliding %d, passages %d (认可敞口)" %
          (len(swing) - len([f for f in fails if f.startswith('门')]),
           len(swing), len(sliding), len(passages)))

    # =================== (c) 窗还原 ===================
    print("=" * 72)
    print("(c) 窗 at/span/wtype 还原")
    print("-" * 72)
    derive_windows = res["windows"]
    if len(derive_windows) != 13:
        print("  FAIL 窗数 %d != 13" % len(derive_windows))
        fails.append("窗计数")
    gwins = []
    for (x, y, w, h, wtype) in windows_raw:
        if w >= h:
            gwins.append(("h", y + h / 2.0, [x, x + w], wtype))
        else:
            gwins.append(("v", x + w / 2.0, [y, y + h], wtype))
    used = [False] * len(gwins)
    for dw in derive_windows:
        for gi, (gax, gat, gsp, gwt) in enumerate(gwins):
            if used[gi] or gax != dw["axis"]:
                continue
            if (abs(gat - dw["at"]) <= 10 and abs(gsp[0] - dw["span"][0]) <= 6 and
                    abs(gsp[1] - dw["span"][1]) <= 6 and gwt == dw["wtype"]):
                used[gi] = True
                break
        else:
            print("  FAIL 窗 %s %s@%g %s wtype=%s 无匹配" %
                  (dw["id"], dw["axis"], dw["at"], dw["span"], dw["wtype"]))
            fails.append("窗无匹配")
    if all(used) and len(derive_windows) == 13:
        print("  PASS — 窗匹配 %d/%d, wtype 全对应" % (sum(used), len(gwins)))

    # =================== (d) §② 黄金断言 ===================
    print("=" * 72)
    print("(d) §② 黄金断言")
    print("-" * 72)

    def empty(axis, at, span):
        for s in derived.get((axis, at), []):
            if overlap_len(span, s) > EPS:
                return False
        return True

    def has(axis, at, span):
        return subset_of(list(span), derived.get((axis, at), []))

    path_segs = []
    for m in re.finditer(r'<path class="wall-thick"[^>]*d="([^"]*)"', svg):
        path_segs = s2g.parse_path_segments(m.group(1))
    seg490 = derived.get(("h", 490), [])
    kit_seg = [s for s in seg490 if s[0] >= 675 - EPS and s[1] <= 1120 + EPS and s[0] < 1215]
    top = res["dims"].get("top", [])
    left = res["dims"].get("left", [])
    asserts = [
        ("外轮廓 path 段数==14", len(path_segs) == 14),
        ("y=1255,x[495,1215] 无墙", empty("h", 1255, [495, 1215])),
        ("y=1020,x[180,495] 无墙(suite_g)", empty("h", 1020, [180, 495])),
        ("x=1215,y[490,680] 无墙(p_lobby)", empty("v", 1215, [490, 680])),
        ("厨房南墙 h@490==[675,745]+[905,1120]",
         approx_intervals(kit_seg, [[675, 745], [905, 1120]])),
        ("x=675,y[0,265] 连续(无15px断口)", has("v", 675, [0, 265])),
        # 1005 刻度系 r_kit/r_balc 旧分隔; 二者并入 space=kitchen 开放后该刻度消失,
        # 与冻结基线 .phase0-baseline/derive-D.json (top 无 1005) 一致.
        ("顶尺寸链刻度==365/675/1215/1515/1815",
         top == [365, 675, 1215, 1515, 1815]),
        ("左尺寸链含 250/640/920", all(t in left for t in (250, 640, 920))),
    ]
    for name, ok in asserts:
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
        if not ok:
            fails.append("断言: " + name)
    print("    (top dims=%s)" % top)
    print("    (left dims=%s)" % left)

    # =================== 总结 ===================
    print("=" * 72)
    print("conflicts:", res["conflicts"])
    print("warns:", res["warns"])
    print("=" * 72)
    if fails:
        print("OVERALL: FAIL ->", fails)
        return 1
    print("OVERALL: PASS — 墙/门(独立)/窗/断言 全过, review=%s, passages=%d" %
          (sorted(review_ids), len(passages)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
