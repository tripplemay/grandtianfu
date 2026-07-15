#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calib-z-b1 F002 一次性迁移: 重跑存量标定的原始输入 -> 写回正确的 camera。

修复前 calibrate() 把世界 z 轴符号系统性取反 (见 aigc/perspective.py 模块 docstring),
存量 camera 因此带病。标定载荷完整保留了原始输入 -> 重跑即可, **无需用户重新标定**。
幂等: 再跑一次会全部报 unchanged, 零改写。

**默认 dry-run —— 只打核对报告, 不写任何文件。** 落盘须显式 --apply。
生产红线 (CLAUDE.md): 生产数据写入须用户明确授权; 先在只读副本上跑 dry-run 核对。

用法 (DATA_DIR = 项目根, 其直接子目录是各项目; 容器内 /data/projects,
宿主 /opt/grandtianfu/data/projects):
    DATA_DIR=/data/projects python3 scripts/migrate_calibration_z.py          # 核对报告
    DATA_DIR=/data/projects python3 scripts/migrate_calibration_z.py --apply  # 落盘
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import baselines  # noqa: E402
from aigc import calib_heal  # noqa: E402


def _room_rects(baseline_dir: str) -> dict:
    """该 baseline 的 {room_id: rect} —— 供报告量化地面位移 (缺失则位移列留空)。"""
    path = os.path.join(baseline_dir, "geometry.json")
    try:
        with open(path, encoding="utf-8") as fh:
            geom = json.load(fh)
        return {r["id"]: r["rect"] for r in geom.get("rooms", []) if r.get("id") and r.get("rect")}
    except Exception:  # noqa: BLE001 - 几何缺失只影响报告的位移列, 不影响自愈本身
        return {}


def _iter_photo_files(data_dir: str):
    """(project_id, version_id, photos.json 路径) —— 遍历所有项目的所有 baseline。"""
    if not os.path.isdir(data_dir):
        return
    for project_id in sorted(os.listdir(data_dir)):
        bl_root = os.path.join(data_dir, project_id, "baselines")
        if not os.path.isdir(bl_root):
            continue
        for version_id in sorted(os.listdir(bl_root)):
            bdir = os.path.join(bl_root, version_id)
            path = os.path.join(bdir, "photos.json")
            if os.path.isfile(path):
                yield project_id, version_id, bdir, path


def main() -> int:
    ap = argparse.ArgumentParser(description="calib-z-b1 F002: 存量标定 z 轴自愈迁移")
    ap.add_argument("--apply", action="store_true", help="真正落盘 (默认 dry-run, 只打报告)")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "data/projects"))
    args = ap.parse_args()

    mode = "APPLY (落盘)" if args.apply else "DRY-RUN (不写任何文件)"
    print(f"[migrate_calibration_z] DATA_DIR={args.data_dir}  模式={mode}")
    print(f"{'project/baseline':>22} {'photo':>14} {'room':>9} {'status':>18} "
          f"{'相机z(前)':>11} {'相机z(后)':>11} {'地面位移px':>11}")

    all_report: list[dict] = []
    written = 0
    for project_id, version_id, bdir, path in _iter_photo_files(args.data_dir):
        with open(path, encoding="utf-8") as fh:
            photos = json.load(fh)
        if not isinstance(photos, list):
            print(f"  {project_id}/{version_id}: photos.json 非数组, 跳过")
            continue
        healed, report = calib_heal.heal_photos(photos, room_rects=_room_rects(bdir))
        for e in report:
            z_before = "" if e["stored_camera_z"] is None else format(e["stored_camera_z"], "+.1f")
            z_after = "" if e["new_camera_z"] is None else format(e["new_camera_z"], "+.1f")
            shift = "" if e["ground_shift_px"] is None else format(e["ground_shift_px"], ".1f")
            where = f"{project_id}/{version_id}"
            print(f"{where:>22} {str(e['photo_id'])[:12]:>14} {str(e['room_id']):>9} "
                  f"{e['status']:>18} {z_before:>11} {z_after:>11} {shift:>11}")
            if e["reason"]:
                print(f"{'':>22} └─ {e['reason']}")
        all_report.extend(report)
        if args.apply and any(e["status"] == "healed" for e in report):
            baselines.atomic_write_json(Path(path), healed, indent=2)
            written += 1

    s = calib_heal.summarize(all_report)
    print("\n" + "=" * 78)
    print(f"合计标定 {s['total']} 条: {s['counts']}")
    print(f"相机在地板下方 (物理不可能): 自愈前 {s['camera_below_floor_before']} 条 -> "
          f"自愈后 {s['camera_below_floor_after']} 条")
    if s["ground_moved"]:
        print(f"地面投影发生移动的 {len(s['ground_moved'])} 条 (『z 朝上但平面被镜像』的解被纠正, "
              f"须用真实照片目检确认):")
        for pid, rid, px in s["ground_moved"]:
            print(f"    {str(pid)[:12]} {rid}: {px} px")
    if args.apply:
        print(f"\n已写入 {written} 个 photos.json (原子写 + 保留 .bak)")
    else:
        print("\nDRY-RUN: 未写入任何文件。确认核对报告无误且获得授权后, 加 --apply 落盘。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
