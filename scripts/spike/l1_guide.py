# -*- coding: utf-8 -*-
"""L1 简模引导图 CLI (calib-cure-b1 F011)。

输入照片(或 --blank 灰底) + 标定 + 几何 + 家具 -> 部件级 3D 简模引导 PNG。

用法:
  python3 scripts/spike/l1_guide.py \\
      --photo /path/to/empty.jpg \\      # 或 --blank (PIPL: 照片路径 CLI 传入, 不入 git)
      --calibration cal.json \\          # {camera:{K,R,t}, img_wh:[W,H]} 或含 calibration 键
      --geometry geometry.json \\        # 产品 geometry (rooms[].rect + meta.mm_per_px)
      --furniture furniture.json \\      # 产品方案家具列表 (或 {items:[...]})
      --room r_live,r_liveext \\         # 可选: 逗号分隔房间过滤 (merge 组请列全成员)
      --out l1_guide.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _product
import parts3d


def load_calibration(path: str) -> dict:
    """标定 JSON: 顶层即 calibration, 或产品 photo 记录 (取其 calibration 键)。"""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    cal = doc.get("calibration") if isinstance(doc.get("calibration"), dict) else doc
    if not isinstance(cal.get("camera"), dict):
        raise SystemExit(f"标定文件缺 camera (K/R/t): {path}")
    if not cal.get("img_wh"):
        raise SystemExit(f"标定文件缺 img_wh: {path}")
    return cal


def load_geometry(path: str) -> tuple:
    """geometry.json -> (rooms_by_id, mm_per_px)。"""
    G = json.loads(Path(path).read_text(encoding="utf-8"))
    rooms = G.get("rooms") or []
    if not rooms:
        raise SystemExit(f"geometry 无 rooms: {path}")
    rooms_by_id = {r["id"]: r["rect"] for r in rooms if r.get("id") and r.get("rect")}
    mm_per_px = float((G.get("meta", {}) or {}).get("mm_per_px", 10))
    return rooms_by_id, mm_per_px


def load_furniture(path: str, rooms: list) -> list:
    """家具 JSON (列表或 {items}) + 可选房间过滤。"""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    items = doc if isinstance(doc, list) else (doc.get("items") or [])
    if not isinstance(items, list):
        raise SystemExit(f"家具文件不是列表/items: {path}")
    if rooms:
        items = [it for it in items if it.get("room_id") in rooms]
    return items


def parse_rooms(arg) -> list:
    return [r.strip() for r in (arg or "").split(",") if r.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L1 简模引导渲染 (产品代码零改动 spike 工具)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--photo", help="空房照路径 (PIPL: 不得放进仓库)")
    src.add_argument("--blank", action="store_true", help="灰底画布替代照片 (离线自证)")
    ap.add_argument("--calibration", required=True, help="标定 JSON (camera + img_wh)")
    ap.add_argument("--geometry", required=True, help="产品 geometry.json")
    ap.add_argument("--furniture", required=True, help="方案家具 JSON")
    ap.add_argument("--room", default="", help="逗号分隔 room_id 过滤 (缺省全部)")
    ap.add_argument("--out", required=True, help="输出 PNG 路径")
    ap.add_argument("--legend-out", default="", help="可选: legend JSON 输出路径")
    args = ap.parse_args(argv)

    persp = _product.load_perspective()
    catalog = _product.load_catalog()
    p2s = _product.load_plan2d_shapes()

    cal = load_calibration(args.calibration)
    cam = persp.Camera.from_dict(cal["camera"])
    img_wh = (int(cal["img_wh"][0]), int(cal["img_wh"][1]))
    rooms_by_id, mm_per_px = load_geometry(args.geometry)
    furn = load_furniture(args.furniture, parse_rooms(args.room))
    if not furn:
        raise SystemExit("过滤后无家具 (检查 --room 与家具文件)")
    photo_png = None if args.blank else Path(args.photo).read_bytes()

    png, legend, drawn = parts3d.render_l1_guide(
        persp, catalog, p2s, cam, furn, rooms_by_id, photo_png, img_wh, mm_per_px=mm_per_px
    )
    if drawn == 0:
        raise SystemExit("无可投影家具 (标注为空); 检查房间过滤与标定")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    if args.legend_out:
        Path(args.legend_out).write_text(
            json.dumps(legend, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        f"L1 引导已写 {out} ({drawn} 件, hfov={parts3d.hfov_deg(cam, img_wh[0]):.1f}°); "
        f"legend: {json.dumps(legend, ensure_ascii=False)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
