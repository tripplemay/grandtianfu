# -*- coding: utf-8 -*-
"""
一键构建:户型几何 + 家具方案 → 2D平面 + 轴测照片底图 + 轴测空壳 → PNG →(可选)自动打开。
用法:
  python3 build.py            # 构建 D户型 全部图并打开预览
  python3 build.py D          # 指定户型
  python3 build.py D --no-open    # 不自动打开
  python3 build.py D --no-geom    # 跳过几何重生成(只改了家具时更快)
单一数据源:几何=平面布置图-无家具.svg(由 平面布置图-生成器.py 产出)；家具=furniture-<户型>.json。
"""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
from floorplan_core import axon as eng
from floorplan_core import prompt_gen
from floorplan_core import geometry

# ============ 户型登记表(新户型在此加一行)============
HOUSES = {
    "D": {
        "geometry_json": f"{HERE}/geometry-D户型.json",    # 几何单一真源(方案B)
        "furniture": f"{HERE}/furniture-D户型.json",       # 家具方案
        "plan_out":  f"{ROOT}/平面布置图.svg",             # 2D含家具平面(输出)
        "outdir":    HERE,                                  # 轴测底图输出目录
        "prefix":    "D户型",
    },
}

def _png(svg, png, w):
    subprocess.run(["rsvg-convert", "-w", str(w), svg, "-o", png], check=True)

def build(name="D", do_geom=True, do_open=True):
    h = HOUSES[name]
    # 几何单一真源: geometry.load -> derive (方案B)。do_geom 仅为兼容旧 flag,已无独立生成器。
    G = geometry.load(h["geometry_json"])
    geo = geometry.derive(G)
    conflicts = geo.get("conflicts", [])
    if conflicts:
        print("⚠ 几何冲突:", conflicts)
    geom = eng.geom_bundle(G, geo)
    furniture = json.load(open(h["furniture"], encoding="utf-8"))
    photo = f'{h["outdir"]}/{h["prefix"]}-照片底图.svg'
    shell = f'{h["outdir"]}/{h["prefix"]}-空壳底图.svg'
    # 同一几何 + 家具 → 平面 + 轴测(照片/空壳)
    eng.render_plan_2d(G, geo, furniture, h["plan_out"])
    eng.render(geom, furniture, photo, mode="photo")
    eng.render(geom, furniture, shell, mode="shell")
    # 提示词随家具表同步刷新 (从几何 G 取房名)
    prompt_gen.write(h["furniture"], G, f'{h["outdir"]}/{h["prefix"]}-4D提示词.txt')
    # 转 PNG
    outs = []
    plan_png = h["plan_out"].replace(".svg", ".png"); _png(h["plan_out"], plan_png, 1600); outs.append(plan_png)
    for svg in (photo, shell):
        png = svg.replace(".svg", ".png"); _png(svg, png, 3200); outs.append(png)
    print("· 完成:", *("\n   "+o for o in outs))
    if do_open and sys.platform == "darwin":
        subprocess.run(["open", plan_png, photo.replace(".svg", ".png")])
    return outs

if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    name = next((a for a in args if not a.startswith("--")), "D")
    build(name, do_geom="--no-geom" not in args, do_open="--no-open" not in args)
