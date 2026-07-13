# -*- coding: utf-8 -*-
"""F001: 缺 rsvg-convert 时渲染端点返可诊断 503 (非裸 500)。

mock 依赖缺失 (shutil.which -> None), 无需真实 rsvg, 有无 librsvg 的环境都可跑。
读真实 data/projects/D (只读) 的几何/家具, 产物指向 tmp。
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from aigc.config import Settings


def _settings(tmp_path):
    return Settings(
        provider="openai",
        base_url="",
        api_key="",
        model="gpt-image-2",
        proxy=None,
        request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"),
        uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5,
        daily_image_cap=10,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    for f in ("geometry.json", "furniture.json"):
        shutil.copyfile(repo_root / "data" / "projects" / "D" / f, project / f)
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "_settings", _settings(tmp_path))
    return TestClient(main.app)


def test_render_png_returns_503_when_rsvg_missing(client, monkeypatch):
    # 模拟本机 dev 无 librsvg: rsvg-convert 不可用 -> 渲染 PNG 应 503 + 可诊断消息。
    monkeypatch.setattr("aigc.raster.shutil.which", lambda _name: None)
    r = client.get("/api/projects/D/render", params={"mode": "plan2d", "format": "png"})
    assert r.status_code == 503, r.text
    assert "rsvg-convert" in r.json()["error"]


def test_render_svg_unaffected_when_rsvg_missing(client, monkeypatch):
    # SVG 格式不经栅格 -> 不受 rsvg 缺失影响 (200), 证明降级只针对 PNG 栅格路径。
    monkeypatch.setattr("aigc.raster.shutil.which", lambda _name: None)
    r = client.get("/api/projects/D/render", params={"mode": "plan2d", "format": "svg"})
    assert r.status_code == 200, r.text
