# -*- coding: utf-8 -*-
"""第7步 render-real: 空房照+轴测参考 多图生成 -> 产物/历史; 照片校验与边界。

读真实 data/projects/D (只读), 产物/预算/上传全指向 tmp。需 rsvg-convert。
"""
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from aigc.artifacts import ArtifactStore
from aigc.budget import BudgetGuard
from aigc.config import Settings
from aigc.providers import ImageResult
from aigc.records import RenderLog

import io

from PIL import Image


def _real_png(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (180, 170, 150)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _real_png()


def _settings(tmp_path, **over):
    base = dict(
        provider="openai", base_url="https://relay/v1", api_key="sk-test", model="gpt-image-2",
        proxy=None, request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"), uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5, daily_image_cap=10,
    )
    base.update(over)
    return Settings(**base)


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def edit(self, prompt, images, *, size="1536x1024", model=None):
        self.calls.append({"prompt": prompt, "images": images, "size": size})
        assert len(images) == 2, "第7步必须是 空房照+轴测参考 两张输入图"
        # 空房照经上传归一化为 JPEG; 轴测参考是 rsvg 输出 PNG。
        assert images[0][:3] == b"\xff\xd8\xff" and images[1][:4] == b"\x89PNG"
        return ImageResult(
            data=b"\x89PNG\r\n\x1a\nREAL", mime="image/png",
            usage={"total_tokens": 7}, model=model or "gpt-image-2",
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "geometry.json", project / "geometry.json")
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "furniture.json", project / "furniture.json")

    s = _settings(tmp_path)
    provider = _FakeProvider()
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    monkeypatch.setattr(main, "_settings", s)
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(s.artifacts_dir))
    monkeypatch.setattr(main, "_uploads", ArtifactStore(s.uploads_dir))
    monkeypatch.setattr(main, "_budget", BudgetGuard(s, path=str(tmp_path / "_b.json")))
    monkeypatch.setattr(main, "_renders", RenderLog(s.artifacts_dir))
    monkeypatch.setattr(main, "get_provider", lambda _s: provider)
    return TestClient(main.app), provider


def _upload_photo(c, room_id="r_live"):
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": room_id, "direction": "N"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _wait(c, jid, t=10.0):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/ai/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job 超时")


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_real_e2e_mocked(client):
    c, provider = client
    photo = _upload_photo(c)

    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    record = job["result"]
    assert record["mode"] == "real-photo"
    assert record["photo_id"] == photo["id"]
    assert record["room_id"] == "r_live"
    assert record["url"].startswith("/api/artifacts/D/default/real-render/")

    # 产物可取回; 历史已记入方案 renders。
    assert c.get(record["url"]).status_code == 200
    renders = c.get("/api/projects/D/schemes/default/renders").json()
    assert any(x.get("id") == record["id"] for x in renders)

    # 提示词含房间语境; 输入图顺序 = 空房照在前。
    call = provider.calls[0]
    assert "空房实拍照片" in call["prompt"]
    assert call["images"][0][:3] == b"\xff\xd8\xff"  # 归一化后的 JPEG 字节


def test_render_real_404_on_unknown_photo(client):
    c, _p = client
    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": "nope"}
    )
    assert r.status_code == 404
    # 预扣已回退: 预算未被占用。
    assert main._budget.status()["daily_count"] == 0


def test_render_real_400_without_photo_id(client):
    c, _p = client
    assert (
        c.post("/api/projects/D/schemes/default/render-real", json={}).status_code
        == 400
    )


def test_render_real_503_when_ai_disabled(client, monkeypatch, tmp_path):
    c, _p = client
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key=""))
    photo = _upload_photo(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert r.status_code == 503
