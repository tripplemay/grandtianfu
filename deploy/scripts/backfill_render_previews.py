#!/usr/bin/env python3
"""一次性回填: 为已存在的 render 记录生成中等预览 (preview_url), 让效果图页主图不再直载
~2MB 全尺寸 PNG (改载 1440px webp ~几百 KB)。新渲染由 main.py 自动产 preview, 本脚本只补历史。

在 api 容器内运行 (自带 Pillow + /data 挂载), 例:
  docker compose -f /opt/grandtianfu/docker-compose.prod.yml exec -T api \
      python - < deploy/scripts/backfill_render_previews.py

幂等: 已有 preview_url 或预览文件已存在则跳过。跳过 .trash。只读原图, 只增预览文件 + 在
renders.json 追加 preview_url 字段 (不动 url/thumb_url, 不删任何东西)。
"""
import glob
import io
import json
import os

from PIL import Image

DATA = os.environ.get("DATA_DIR", "/data/projects")
ARTIFACTS = os.environ.get("ARTIFACTS_DIR", "/data/artifacts")
PREFIX = "/api/artifacts/"
PREVIEW_EDGE = 1440
PREVIEW_QUALITY = 82


def make_preview(png_path: str) -> bytes:
    img = Image.open(png_path)
    img.load()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=PREVIEW_QUALITY)
    return out.getvalue()


def atomic_write(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


made = 0
files = 0
for rj in glob.glob(os.path.join(DATA, "*", "schemes", "*", "renders.json")):
    if ".trash" in rj:
        continue
    try:
        recs = json.load(open(rj, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("skip (read fail):", rj, exc)
        continue
    if not isinstance(recs, list):
        continue
    dirty = False
    for r in recs:
        if not isinstance(r, dict) or r.get("preview_url"):
            continue
        url = r.get("url") or ""
        if not url.startswith(PREFIX) or "-render/" not in url:
            continue
        rel = url[len(PREFIX):]                         # D/default/real-render/<uuid>.png
        png_path = os.path.join(ARTIFACTS, rel)
        if not os.path.exists(png_path):
            print("missing png:", png_path)
            continue
        preview_rel = rel.replace("-render/", "-preview/").rsplit(".", 1)[0] + ".webp"
        preview_path = os.path.join(ARTIFACTS, preview_rel)
        try:
            os.makedirs(os.path.dirname(preview_path), exist_ok=True)
            if not os.path.exists(preview_path):
                atomic_write(preview_path, make_preview(png_path))
                os.chmod(preview_path, 0o644)           # nginx (www-data) 需 o+r
            r["preview_url"] = PREFIX + preview_rel
            dirty = True
            made += 1
        except Exception as exc:  # noqa: BLE001
            print("preview fail:", png_path, exc)
    if dirty:
        atomic_write(rj, json.dumps(recs, ensure_ascii=False).encode("utf-8"))
        files += 1
        print("updated:", rj)

print(f"done: {made} previews backfilled across {files} renders.json")
