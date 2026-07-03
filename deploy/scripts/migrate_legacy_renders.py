# -*- coding: utf-8 -*-
"""一次性迁移 (审计 P2 legacy 收口): ARTIFACTS_DIR/{pid}/renders.json (RenderLog 旧账本)
并入 data/projects/{pid}/schemes/default/renders.json, 按 id/url 去重, 迁完清空旧账本。

幂等: 重跑无副作用。用法 (容器内):
    docker exec grandtianfu-api-1 python /app/deploy/scripts/migrate_legacy_renders.py
或宿主: DATA_DIR=... ARTIFACTS_DIR=... python3 deploy/scripts/migrate_legacy_renders.py
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data/projects"))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", "/data/artifacts"))


def main() -> None:
    moved = 0
    for legacy_path in sorted(ARTIFACTS_DIR.glob("*/renders.json")):
        pid = legacy_path.parent.name
        try:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {legacy_path}: {exc}")
            continue
        if not isinstance(legacy, list) or not legacy:
            continue
        target = DATA_DIR / pid / "schemes" / "default" / "renders.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(current, list):
                current = []
        except FileNotFoundError:
            current = []
        seen = {str(r.get("id") or r.get("url")) for r in current if isinstance(r, dict)}
        fresh = [
            r
            for r in legacy
            if isinstance(r, dict) and str(r.get("id") or r.get("url")) not in seen
        ]
        if fresh:
            merged = [*current, *fresh][:200]
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)
            moved += len(fresh)
        # 清空旧账本 (保留空数组占位, RenderLog 读到空即 no-op)
        tmp = legacy_path.with_name(legacy_path.name + ".tmp")
        tmp.write_text("[]", encoding="utf-8")
        os.replace(tmp, legacy_path)
        print(f"[ok] {pid}: merged {len(fresh)} legacy records -> {target}")
    print(f"[done] migrated {moved} records")


if __name__ == "__main__":
    main()
