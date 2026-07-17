# -*- coding: utf-8 -*-
"""L0 彩盒 vs L1 简模 A/B 出图编排 (calib-cure-b1 F011; 执行权在 F012/Evaluator)。

对每个场景 × {L0, L1} × {relay, fal} 出图并记账:
  - L0 臂: 产品 `perspective.annotate_boxes` 逐字调用 + 产品 prompt 模板逐字
    (`_geometry_lock_prompt` 复制自 apps/api/main.py:2263-2353);
  - L1 臂: 同一 prompt 结构, 仅把「彩盒→家具」映射段替换为简模措辞 (spec §D5 公平性:
    同 photo / 同 camera / 同 furniture / 同 size, rug/墙面带/附着/边缘话术全保留);
  - 量化: 产品 `acceptance.evaluate_geometry_lock` (auto_check 同款) +
    `eval_harness.classify_failures`; 每图记 usage tokens (relay) / 输出像素 (fal)。

预算红线: 出图动作只应由 F012 (Evaluator, 用户已授权预算) 执行; 本脚本默认建议先跑
`--dry` (只产两臂引导图与 prompt, 不调 provider, 零成本可复现)。

用法:
  python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ --dry
  python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ \\
      --backends relay,fal --arms L0,L1        # 真实出图 (需 OPENAI_*/FAL_KEY 环境变量)

scenes.json (路径相对清单文件所在目录解析; photo="blank" 用灰底):
  [{"id": "study_798", "photo": "/local/untracked/empty.jpg",
    "calibration": "cal_798.json", "geometry": "geometry.json",
    "furniture": "furniture.json", "rooms": ["r_guest2"],
    "style": "modern light-luxury (现代轻奢)"}]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional

import _product
import l1_guide as _l1cli
import parts3d

# 产品模块 (importlib 路径加载, 见 _product; _init_modules() 填充)。
persp = None
catalog = None
p2s = None

ARMS = ("L0", "L1")
BACKENDS = ("relay", "fal")


def _init_modules() -> None:
    global persp, catalog, p2s
    if persp is None:
        persp = _product.load_perspective()
        catalog = _product.load_catalog()
        p2s = _product.load_plan2d_shapes()


# ---------------------------------------------------------------------------
# L0 prompt —— **逐字复制**自产品 apps/api/main.py:2263-2353 `_geometry_lock_prompt`
# (spec §D5: spike 不 import main.py, prompt 模板拷贝进脚本并注明来源行号)。
# 除去掉产品 docstring 外, 函数体与产品逐字一致; `catalog` 为 importlib 加载的
# 同一份产品目录模块 (CATALOG/attach_en 单一真源)。
# ---------------------------------------------------------------------------
def _geometry_lock_prompt(legend: list, furniture: list, style: Optional[str]) -> str:
    parts: list = []
    edge_notes: list = []
    for entry in legend:
        en = (catalog.CATALOG.get(entry["t"]) or {}).get("en")
        if not en:
            continue
        count = int(entry.get("count") or 1)
        if count > 1:
            parts.append(f"{entry['color']} boxes = {en} ({count} pieces, one per box)")
        else:
            parts.append(f"{entry['color']} box = {en}")
        if entry.get("near"):
            edge_notes.append(
                f"The {entry['color']} {en} sits in the near foreground close to the camera: "
                "render it at full foreground scale where its box is — do not shrink it into the "
                "background or push it deeper into the room."
            )
        elif entry.get("partial"):
            edge_notes.append(
                f"The {entry['color']} {en} is partly outside the frame at the image edge: render "
                "only its visible part in place — do not invent or complete the hidden portion."
            )
    mapping = "; ".join(parts) if parts else "the scheme furniture"
    style_txt = style or "modern light-luxury (现代轻奢)"
    rug_txt = (
        " Add an area rug on the floor under the seating."
        if any(it.get("t") == "rug" for it in furniture)
        else ""
    )
    wall_decor_notes: list = []
    if any(it.get("t") == "wall_art" for it in furniture):
        wall_decor_notes.append(
            "The framed wall art marker sits high on the wall: render it as flat framed artwork "
            "mounted on the wall, centered above the furniture beneath it — not a freestanding "
            "object on the floor."
        )
    if any(it.get("t") == "curtain" for it in furniture):
        wall_decor_notes.append(
            "The curtain marker is on the wall beside the window: render floor-length curtains "
            "hanging over the window, not a solid boxy object."
        )
    wall_decor_txt = (" " + " ".join(wall_decor_notes)) if wall_decor_notes else ""
    attach_ens: list = []
    seen_attach: set = set()
    for it in furniture:
        for d in it.get("decor") or []:
            dt = d.get("t")
            en = catalog.attach_en(dt)
            if en and dt not in seen_attach:
                seen_attach.add(dt)
                attach_ens.append(en)
    attach_txt = (
        " Style the furniture with tasteful soft furnishings: " + ", ".join(attach_ens) + "."
        if attach_ens
        else ""
    )
    edge_txt = (" " + " ".join(edge_notes)) if edge_notes else ""
    return (
        "Image 1 is a real photo of an empty room. Image 2 is the same photo with colored "
        "translucent boxes marking where furniture must be placed. Produce a photorealistic "
        f"version of image 1 furnished exactly according to image 2's layout: {mapping}. "
        "Each piece must be a real, solid, three-dimensional piece of furniture that fills its "
        f"box's footprint, height and orientation, in {style_txt} style. The box colors are "
        "position markers only — do NOT use them as furniture colors; choose realistic "
        "materials fitting the style."
        + rug_txt
        + wall_decor_txt
        + attach_txt
        + edge_txt
        + " Keep image 1's camera angle, walls, windows, floor, ceiling, materials and lighting "
        "exactly unchanged, and add realistic floor reflections and contact shadows under the "
        "new furniture. Every colored box must be erased and replaced by its furniture; the "
        "output must contain no colored boxes, overlays or text — only real furniture."
    )


def _l1_mockup_prompt(legend: list, furniture: list, style: Optional[str]) -> str:
    """L1 臂 prompt: 与 L0 同结构同语段, **仅替换「彩盒→家具」映射段为简模措辞**
    (spec §D5 两臂公平性: rug/墙面带/附着/边缘降级话术保持同语义, 只去掉颜色指涉)。"""
    parts: list = []
    edge_notes: list = []
    for entry in legend:
        en = (catalog.CATALOG.get(entry["t"]) or {}).get("en")
        if not en:
            continue
        count = int(entry.get("count") or 1)
        if count > 1:
            parts.append(f"{en} ({count} pieces, one per mockup)")
        else:
            parts.append(f"{en}")
        if entry.get("near"):
            edge_notes.append(
                f"The {en} sits in the near foreground close to the camera: render it at full "
                "foreground scale where its mockup is — do not shrink it into the background or "
                "push it deeper into the room."
            )
        elif entry.get("partial"):
            edge_notes.append(
                f"The {en} is partly outside the frame at the image edge: render only its "
                "visible part in place — do not invent or complete the hidden portion."
            )
    mapping = "; ".join(parts) if parts else "the scheme furniture"
    style_txt = style or "modern light-luxury (现代轻奢)"
    rug_txt = (
        " Add an area rug on the floor under the seating."
        if any(it.get("t") == "rug" for it in furniture)
        else ""
    )
    wall_decor_notes: list = []
    if any(it.get("t") == "wall_art" for it in furniture):
        wall_decor_notes.append(
            "The framed wall art marker sits high on the wall: render it as flat framed artwork "
            "mounted on the wall, centered above the furniture beneath it — not a freestanding "
            "object on the floor."
        )
    if any(it.get("t") == "curtain" for it in furniture):
        wall_decor_notes.append(
            "The curtain marker is on the wall beside the window: render floor-length curtains "
            "hanging over the window, not a solid boxy object."
        )
    wall_decor_txt = (" " + " ".join(wall_decor_notes)) if wall_decor_notes else ""
    attach_ens: list = []
    seen_attach: set = set()
    for it in furniture:
        for d in it.get("decor") or []:
            dt = d.get("t")
            en = catalog.attach_en(dt)
            if en and dt not in seen_attach:
                seen_attach.add(dt)
                attach_ens.append(en)
    attach_txt = (
        " Style the furniture with tasteful soft furnishings: " + ", ".join(attach_ens) + "."
        if attach_ens
        else ""
    )
    edge_txt = (" " + " ".join(edge_notes)) if edge_notes else ""
    return (
        "Image 1 is a real photo of an empty room. Image 2 is the same photo with gray 3D "
        "primitive mockups showing each furniture piece in its exact position, size and shape: "
        f"{mapping}. Produce a photorealistic version of image 1 furnished exactly according to "
        "image 2's layout: replace each mockup with a real, photorealistic piece of furniture "
        "matching its exact position, footprint, height, shape and orientation, in "
        f"{style_txt} style. The mockups are placement guides only — do NOT copy their flat "
        "gray look; choose realistic materials fitting the style."
        + rug_txt
        + wall_decor_txt
        + attach_txt
        + edge_txt
        + " Keep image 1's camera angle, walls, windows, floor, ceiling, materials and lighting "
        "exactly unchanged, and add realistic floor reflections and contact shadows under the "
        "new furniture. Every gray mockup must be erased and replaced by its furniture; the "
        "output must contain no gray primitive shapes, overlays or text — only real furniture."
    )


def _edit_once(
    settings,
    providers,
    raster,
    backend: str,
    prompt: str,
    empty_png: bytes,
    guide_png: bytes,
    img_wh,
) -> tuple:
    """出图调用 —— 参照产品 main.py:2475-2487 `_edit_once` 的两后端调用形态。"""
    if backend == "fal":
        size_str = f"{img_wh[0]}x{img_wh[1]}"  # fal 不收尺寸参数, 请求档记照片档
        res = providers.get_fal_provider(settings).edit(prompt, [empty_png, guide_png])
    else:
        # relay 按照片纵横比选输出档 (比例不符会让模型重取景, 违反保结构)。
        edit_size = raster.pick_edit_size(img_wh[0], img_wh[1])
        size_str = f"{edit_size[0]}x{edit_size[1]}"
        res = providers.get_provider(settings).edit(
            prompt, [empty_png, guide_png], size=size_str, model=settings.model
        )
    return res, size_str


def _png_size(data: bytes) -> str:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as im:
            return f"{im.size[0]}x{im.size[1]}"
    except Exception:  # noqa: BLE001 - 尺寸读取失败不阻断记账
        return "?"


def _load_scene(scene: dict, base: Path) -> dict:
    """清单条目 -> 就绪场景 (相对路径按清单目录解析)。"""

    def rp(key: str) -> str:
        v = scene.get(key)
        if not v:
            raise SystemExit(f"场景 {scene.get('id')} 缺 {key}")
        p = Path(v)
        return str(p if p.is_absolute() else base / p)

    cal = _l1cli.load_calibration(rp("calibration"))
    cam = persp.Camera.from_dict(cal["camera"])
    img_wh = (int(cal["img_wh"][0]), int(cal["img_wh"][1]))
    rooms_by_id, mm_per_px = _l1cli.load_geometry(rp("geometry"))
    furn = _l1cli.load_furniture(rp("furniture"), list(scene.get("rooms") or []))
    if not furn:
        raise SystemExit(f"场景 {scene.get('id')}: 过滤后无家具")
    photo = scene.get("photo") or "blank"
    if photo == "blank":
        empty_png = parts3d.blank_photo_png(img_wh)
    else:
        p = Path(photo)
        empty_png = (p if p.is_absolute() else base / p).read_bytes()
    return {
        "id": str(scene.get("id") or "scene"),
        "cam": cam,
        "img_wh": img_wh,
        "rooms_by_id": rooms_by_id,
        "mm_per_px": mm_per_px,
        "furn": furn,
        "empty_png": empty_png,
        "style": scene.get("style"),
    }


def _build_guides(sc: dict, outdir: Path, arms: list, force: bool) -> dict:
    """两臂引导图 + prompt 落盘 -> {arm: {guide_png, prompt, legend, files...}}。"""
    issues = persp.guide_sanity_issues(
        sc["cam"], sc["furn"], sc["rooms_by_id"], sc["img_wh"], mm_per_px=sc["mm_per_px"]
    )
    if issues:
        msg = f"场景 {sc['id']} 引导退化: " + "; ".join(issues)
        if not force:
            raise SystemExit(msg + " (--force 可强行继续, 但会烧钱出错图)")
        print(f"[warn] {msg} (--force 已忽略)")
    out: dict = {}
    for arm in arms:
        if arm == "L0":
            guide_png, legend, drawn = persp.annotate_boxes(
                sc["cam"],
                sc["furn"],
                sc["rooms_by_id"],
                sc["empty_png"],
                sc["img_wh"],
                mm_per_px=sc["mm_per_px"],
            )
            prompt = _geometry_lock_prompt(legend, sc["furn"], sc["style"])
        else:
            guide_png, legend, drawn = parts3d.render_l1_guide(
                persp,
                catalog,
                p2s,
                sc["cam"],
                sc["furn"],
                sc["rooms_by_id"],
                sc["empty_png"],
                sc["img_wh"],
                mm_per_px=sc["mm_per_px"],
            )
            prompt = _l1_mockup_prompt(legend, sc["furn"], sc["style"])
        if drawn == 0:
            raise SystemExit(f"场景 {sc['id']} {arm}: 无可投影家具")
        gfile = outdir / f"{sc['id']}_{arm}_guide.png"
        pfile = outdir / f"{sc['id']}_{arm}_prompt.txt"
        gfile.write_bytes(guide_png)
        pfile.write_text(prompt, encoding="utf-8")
        out[arm] = {
            "guide_png": guide_png,
            "prompt": prompt,
            "legend": legend,
            "drawn": drawn,
            "guide_file": gfile.name,
        }
    return out


def _run_scene(
    sc: dict,
    guides: dict,
    outdir: Path,
    backends: list,
    settings,
    providers,
    raster,
    acceptance,
    eval_harness,
) -> list:
    """单场景真实出图: 每 (arm, backend) 一图 + evaluate + usage 记账。"""
    rows: list = []
    for arm, g in guides.items():
        for backend in backends:
            row = {
                "scene": sc["id"],
                "arm": arm,
                "backend": backend,
                "provider_ok": False,
                "model": None,
                "requested_size": None,
                "actual_size": None,
                "score": None,
                "auto_ok": None,
                "fail_reasons": [],
                "failure_types": [],
                "total_tokens": None,
                "fal_px": None,
                "out_file": None,
                "error": None,
                "elapsed_s": None,
            }
            enabled = settings.fal_enabled if backend == "fal" else settings.ai_enabled
            if not enabled:
                row["error"] = f"{backend} 未配置 (缺 " + (
                    "FAL_KEY)" if backend == "fal" else "OPENAI_API_KEY/OPENAI_BASE_URL)"
                )
                rows.append(row)
                print(f"[skip] {sc['id']} {arm} {backend}: {row['error']}")
                continue
            t0 = time.time()
            try:
                res, size_str = _edit_once(
                    settings,
                    providers,
                    raster,
                    backend,
                    g["prompt"],
                    sc["empty_png"],
                    g["guide_png"],
                    sc["img_wh"],
                )
            except Exception as exc:  # noqa: BLE001 - 单图失败不拖垮整批
                row["error"] = f"{type(exc).__name__}: {exc}"
                row["elapsed_s"] = round(time.time() - t0, 1)
                rows.append(row)
                print(f"[fail] {sc['id']} {arm} {backend}: {row['error']}")
                continue
            row["elapsed_s"] = round(time.time() - t0, 1)
            row["provider_ok"] = True
            row["model"] = res.model
            row["requested_size"] = size_str
            row["actual_size"] = _png_size(res.data)
            usage = res.usage or {}
            if backend == "fal":
                w, h = usage.get("width"), usage.get("height")
                row["fal_px"] = f"{w}x{h}" if w and h else None
            else:
                tt = usage.get("total_tokens")
                row["total_tokens"] = int(tt) if isinstance(tt, (int, float)) else None
            ofile = outdir / f"{sc['id']}_{arm}_{backend}.png"
            ofile.write_bytes(res.data)
            row["out_file"] = ofile.name
            try:
                verdict = acceptance.evaluate_geometry_lock(
                    sc["empty_png"],
                    res.data,
                    guide_png=g["guide_png"],
                    cam=sc["cam"],
                    furniture=sc["furn"],
                    rooms_by_id=sc["rooms_by_id"],
                    img_wh=sc["img_wh"],
                    mm_per_px=sc["mm_per_px"],
                )
                row["auto_ok"] = bool(verdict.get("ok"))
                row["score"] = verdict.get("score")
                row["fail_reasons"] = list(verdict.get("fail_reasons") or [])
                row["failure_types"] = eval_harness.classify_failures(row["fail_reasons"])
            except Exception as exc:  # noqa: BLE001 - 验收出错记账但不丢图
                row["fail_reasons"] = [f"验收执行失败: {exc}"]
            rows.append(row)
            print(
                f"[done] {sc['id']} {arm} {backend}: score={row['score']} "
                f"tokens={row['total_tokens']} px={row['fal_px']} -> {row['out_file']}"
            )
    return rows


def _cell(v) -> str:
    if v is True:
        return "✅"
    if v is False:
        return "❌"
    if v is None:
        return "—"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v) if v else "—"
    return str(v)


def _write_summary(rows: list, outdir: Path, dry: bool) -> Path:
    """汇总 markdown (场景×引导×后端×score/fails/tokens) + rows.json。"""
    md: list = ["# spike L0/L1 A/B 出图汇总", ""]
    if dry:
        md += ["> `--dry` 干跑: 只产两臂引导图, 未调 provider (零成本)。", ""]
        md.append("| 场景 | 引导 | 件数 | 引导图 | prompt |")
        md.append("| --- | --- | --- | --- | --- |")
        for r in rows:
            md.append(
                f"| {r['scene']} | {r['arm']} | {r['drawn']} | {r['guide_file']} "
                f"| {r['prompt_file']} |"
            )
    else:
        md.append(
            "| 场景 | 引导 | 后端 | 出图 | score | 自动验收 | 失败类型 | fail_reasons "
            "| tokens | fal像素 | 耗时s | 文件 |"
        )
        md.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in rows:
            md.append(
                f"| {r['scene']} | {r['arm']} | {r['backend']} | {_cell(r['provider_ok'])} "
                f"| {_cell(r['score'])} | {_cell(r['auto_ok'])} | {_cell(r['failure_types'])} "
                f"| {_cell(r['fail_reasons'] or r['error'])} | {_cell(r['total_tokens'])} "
                f"| {_cell(r['fal_px'])} | {_cell(r['elapsed_s'])} | {_cell(r['out_file'])} |"
            )
        tokens = sum(r["total_tokens"] or 0 for r in rows)
        mp = 0.0
        for r in rows:
            if r.get("fal_px"):
                w, _, h = r["fal_px"].partition("x")
                try:
                    mp += int(w) * int(h) / 1e6
                except ValueError:
                    pass
        md += [
            "",
            "## 预算记账",
            f"- 出图 {sum(1 for r in rows if r['provider_ok'])}/{len(rows)} 成功",
            f"- relay tokens 合计: {tokens}",
            f"- fal 输出像素合计: {mp:.2f} MP (按 fal 模型单价换算费用)",
        ]
    sfile = outdir / "summary.md"
    sfile.write_text("\n".join(md) + "\n", encoding="utf-8")
    (outdir / "rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return sfile


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L0/L1 × relay/fal A/B 出图编排 (产品零改动)")
    ap.add_argument("--scenes", required=True, help="场景清单 JSON (见模块 docstring)")
    ap.add_argument("--outdir", required=True, help="输出目录 (图/prompt/summary.md/rows.json)")
    ap.add_argument(
        "--dry", action="store_true", help="只产两臂引导图与 prompt, 不调 provider (零成本自证)"
    )
    ap.add_argument("--arms", default="L0,L1", help="逗号分隔: L0,L1")
    ap.add_argument("--backends", default="relay,fal", help="逗号分隔: relay,fal")
    ap.add_argument("--force", action="store_true", help="引导退化时仍继续 (默认阻断)")
    args = ap.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    bad = [a for a in arms if a not in ARMS] + [b for b in backends if b not in BACKENDS]
    if bad:
        raise SystemExit(f"未知 arm/backend: {bad} (arms∈{ARMS}, backends∈{BACKENDS})")

    _init_modules()
    scenes_path = Path(args.scenes)
    manifest = json.loads(scenes_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise SystemExit("场景清单必须是非空 JSON 数组")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    settings = providers = raster = acceptance = eval_harness = None
    if not args.dry:
        # 懒加载 aigc 包 (httpx 依赖只在真实出图时需要)。
        config = _product.import_aigc("config")
        providers = _product.import_aigc("providers")
        raster = _product.import_aigc("raster")
        acceptance = _product.import_aigc("acceptance")
        eval_harness = _product.import_aigc("eval_harness")
        settings = config.get_settings()

    rows: list = []
    for scene in manifest:
        sc = _load_scene(scene, scenes_path.resolve().parent)
        guides = _build_guides(sc, outdir, arms, args.force)
        if args.dry:
            for arm, g in guides.items():
                rows.append(
                    {
                        "scene": sc["id"],
                        "arm": arm,
                        "dry": True,
                        "drawn": g["drawn"],
                        "guide_file": g["guide_file"],
                        "prompt_file": f"{sc['id']}_{arm}_prompt.txt",
                        "legend": g["legend"],
                    }
                )
                print(f"[dry] {sc['id']} {arm}: {g['drawn']} 件 -> {g['guide_file']}")
        else:
            rows.extend(
                _run_scene(
                    sc,
                    guides,
                    outdir,
                    backends,
                    settings,
                    providers,
                    raster,
                    acceptance,
                    eval_harness,
                )
            )
    sfile = _write_summary(rows, outdir, args.dry)
    print(f"汇总已写 {sfile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
