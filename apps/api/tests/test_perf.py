# -*- coding: utf-8 -*-
"""性能特征测试 (审计 P2-3 验收): 读侧载荷瘦身 + 关键热路径耗时上限。

耗时上限取宽松值 (CI 慢机不误报), 主要锁定确定性特征 (载荷内容/截断行为)。"""
import io
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import main
from floorplan_core import geometry, layout


def _write_project(root: Path) -> None:
    project = root / "D"
    project.mkdir(parents=True)
    repo_root = Path(__file__).resolve().parents[3]
    for name in ("geometry.json", "furniture.json"):
        (project / name).write_text(
            (repo_root / "data" / "projects" / "D" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _client(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    _write_project(root)
    monkeypatch.setattr(main, "DATA_DIR", str(root))
    return TestClient(main.app), root


def _seed_renders(root: Path, count: int = 200) -> None:
    """直接落盘 200 条含胖 manifest 的历史 (模拟 cap 满)。"""
    scheme_dir = root / "D" / "schemes" / "default"
    scheme_dir.mkdir(parents=True, exist_ok=True)
    fat_manifest = {"scene_hash": "x" * 64, "prompt": "p" * 800, "validation": {"errors": 0}}
    records = [
        {
            "id": f"r{i}",
            "url": f"/api/artifacts/D/default/ai-render/r{i}.png",
            "mode": "axon-photoreal",
            "model": "gpt-image-2",
            "prompt": "K" * 900,
            "usage": {"total_tokens": 12345, "input_tokens": 111},
            "scene_manifest": fat_manifest,
        }
        for i in range(count)
    ]
    (scheme_dir / "renders.json").write_text(json.dumps(records), encoding="utf-8")
    (scheme_dir / "furniture.json").write_text("[]", encoding="utf-8")
    (scheme_dir / "meta.json").write_text(
        json.dumps({"id": "default", "name": "初始方案", "source": "legacy", "status": "draft"}),
        encoding="utf-8",
    )


def test_renders_list_default_is_thin_and_fast(tmp_path, monkeypatch):
    client, root = _client(tmp_path, monkeypatch)
    _seed_renders(root, 200)

    t0 = time.monotonic()
    resp = client.get("/api/projects/D/schemes/default/renders")
    elapsed = time.monotonic() - t0
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 200
    # 载荷瘦身: 重字段全部剥离, 总载荷显著小于全量。
    assert all(
        "scene_manifest" not in r and "usage" not in r and "prompt" not in r
        for r in records
    )
    thin_bytes = len(resp.content)
    full = client.get("/api/projects/D/schemes/default/renders?detail=1")
    assert len(full.content) > thin_bytes * 3
    assert full.json()[0]["scene_manifest"]["scene_hash"] == "x" * 64
    # 宽松耗时上限 (200 条 JSON 读+瘦身应为毫秒级)。
    assert elapsed < 1.0, f"renders list too slow: {elapsed:.3f}s"

    limited = client.get("/api/projects/D/schemes/default/renders?limit=5").json()
    assert [r["id"] for r in limited] == [f"r{i}" for i in range(5)]


def test_layout_plan_report_full_house_under_bound():
    repo_root = Path(__file__).resolve().parents[3]
    G = geometry.load(repo_root / "data" / "projects" / "D" / "geometry.json")
    selections = [
        {
            "room_id": r["id"],
            "items": [
                {"t": "sofa", "count": 2},
                {"t": "bed", "count": 1},
                {"t": "plant", "count": 3},
                {"t": "wardrobe", "count": 2},
            ],
        }
        for r in G["rooms"]
    ]

    t0 = time.monotonic()
    for _ in range(5):
        items, _warns = layout.plan_report(G, selections)
    elapsed = (time.monotonic() - t0) / 5
    assert items
    assert elapsed < 0.5, f"plan_report too slow: {elapsed:.3f}s/次"


def test_normalize_photo_large_image_under_bound():
    from aigc.imaging import normalize_photo

    buf = io.BytesIO()
    Image.new("RGB", (2400, 1600), (150, 140, 130)).save(buf, format="JPEG", quality=95)

    t0 = time.monotonic()
    blob, meta = normalize_photo(buf.getvalue())
    elapsed = time.monotonic() - t0
    assert max(meta["width"], meta["height"]) <= 2048
    assert elapsed < 2.0, f"normalize too slow: {elapsed:.3f}s"
