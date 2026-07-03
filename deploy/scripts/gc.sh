#!/usr/bin/env bash
# 产物垃圾回收 (审计 P2-2): mark-and-sweep 清理无引用的 artifacts/uploads 文件。
#
# 引用并集 (mark):
#   - 所有方案 (含 .trash 内) renders.json 的 url/thumb_url/base_url
#   - 所有户型版本 (含 superseded) photos.json 的 url/thumb_url
# 清理 (sweep): 引用集之外、且 mtime 早于 N 天 (默认 7) 的文件。
# 默认 dry-run 只打印; 传 --apply 才真删。.trash 目录按 30 天淘汰。
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-/opt/grandtianfu/data}"
GRACE_DAYS="${GC_GRACE_DAYS:-7}"
TRASH_DAYS="${GC_TRASH_DAYS:-30}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

command -v python3 >/dev/null || { echo "需要 python3" >&2; exit 1; }

python3 - "$DATA_ROOT" "$GRACE_DAYS" "$APPLY" <<'PY'
import json, os, sys, time
from pathlib import Path

data_root = Path(sys.argv[1]); grace_days = float(sys.argv[2]); apply = sys.argv[3] == "1"
projects = data_root / "projects"; artifacts = data_root / "artifacts"; uploads = data_root / "uploads"
cutoff = time.time() - grace_days * 86400

referenced: set[str] = set()

def mark_urls(payload):
    if isinstance(payload, list):
        for rec in payload:
            if isinstance(rec, dict):
                for key in ("url", "thumb_url", "base_url", "photo_url"):
                    v = rec.get(key)
                    if isinstance(v, str):
                        for prefix, root in (("/api/artifacts/", artifacts), ("/api/uploads/", uploads)):
                            if v.startswith(prefix):
                                referenced.add(str((root / v[len(prefix):]).resolve()))

for path in projects.rglob("renders.json"):
    try: mark_urls(json.loads(path.read_text(encoding="utf-8")))
    except Exception: pass
for path in projects.rglob("photos.json"):
    try: mark_urls(json.loads(path.read_text(encoding="utf-8")))
    except Exception: pass
# legacy: ARTIFACTS 根下项目级 renders.json (RenderLog 旧账本)
for path in artifacts.glob("*/renders.json"):
    try: mark_urls(json.loads(path.read_text(encoding="utf-8")))
    except Exception: pass

freed = 0; count = 0
for root in (artifacts, uploads):
    if not root.exists(): continue
    for f in root.rglob("*"):
        if not f.is_file() or f.name == "renders.json" or f.name.startswith("_"):
            continue  # 账本/簿记文件不清 (_budget.json 等)
        if str(f.resolve()) in referenced or f.stat().st_mtime > cutoff:
            continue
        count += 1; freed += f.stat().st_size
        print(("DELETE " if apply else "would-delete ") + str(f))
        if apply: f.unlink()

print(f"[gc] {'deleted' if apply else 'candidates'}: {count} files, {freed/1024/1024:.1f} MB "
      f"(referenced={len(referenced)}, grace={grace_days}d)")
PY

# .trash 淘汰 (方案软删目录)
find "$DATA_ROOT/projects" -type d -path '*/.trash/*' -mtime +"$TRASH_DAYS" -prune 2>/dev/null | while read -r d; do
  if [ "$APPLY" = "1" ]; then echo "DELETE $d"; rm -rf "$d"; else echo "would-delete $d"; fi
done
echo "[gc] done (apply=$APPLY)"
