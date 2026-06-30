# -*- coding: utf-8 -*-
"""render-ai 端点 (Phase 2): mock provider 跑通 异步生成->产物->历史; 503/402 边界。

读真实 data/projects/D (只读), 产物/预算/历史全指向 tmp (不污染仓库)。需 rsvg-convert。
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


def _settings(tmp_path, **over):
    base = dict(
        provider="openai", base_url="https://relay/v1", api_key="sk-test", model="gpt-image-2",
        proxy=None, request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"), uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5, daily_image_cap=10,
    )
    base.update(over)
    return Settings(**base)


def _create_scheme(c, scheme_id="scheme_manual_001"):
    r = c.post(
        "/api/projects/D/schemes",
        json={
            "id": scheme_id,
            "name": "方案 A",
            "source": "manual",
            "furniture": [
                {"t": "sofa", "w": 100, "h": 80, "room_id": "r_live", "dx": 10, "dy": 10}
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


class _FakeProvider:
    def edit(self, prompt, images, *, size="1536x1024", model=None):
        assert images and isinstance(images[0], (bytes, bytearray)) and images[0][:4] == b"\x89PNG"
        assert isinstance(prompt, str) and "isometric" in prompt
        return ImageResult(data=b"\x89PNG\r\n\x1a\nFAKE", mime="image/png",
                           usage={"total_tokens": 42}, model=model or "gpt-image-2")


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "geometry.json", project / "geometry.json")
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "furniture.json", project / "furniture.json")

    s = _settings(tmp_path)
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "_settings", s)
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(s.artifacts_dir))
    monkeypatch.setattr(main, "_budget", BudgetGuard(s, path=str(tmp_path / "_b.json")))
    monkeypatch.setattr(main, "_renders", RenderLog(s.artifacts_dir))
    monkeypatch.setattr(main, "get_provider", lambda _s: _FakeProvider())
    return TestClient(main.app), tmp_path


def _wait(c, jid, t=10.0):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/ai/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job 超时")


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_ai_e2e_mocked(client):
    c, _ = client
    r = c.post("/api/projects/D/render-ai")
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    url = job["result"]["url"]
    assert url.startswith("/api/artifacts/D/default/ai-render/") and url.endswith(".png")
    assert job["result"]["with_positions"] is True
    assert c.get(url).status_code == 200            # 产物可服务
    lst = c.get("/api/projects/D/renders").json()    # 历史含该记录
    assert any(x["url"] == url for x in lst)


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_scheme_render_ai_e2e_mocked(client):
    c, _ = client
    _create_scheme(c)

    r = c.post("/api/projects/D/schemes/scheme_manual_001/render-ai")
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])

    assert job["status"] == "done", job
    url = job["result"]["url"]
    assert url.startswith("/api/artifacts/D/scheme_manual_001/ai-render/")
    assert url.endswith(".png")
    assert job["result"]["scheme_id"] == "scheme_manual_001"
    assert c.get(url).status_code == 200
    assert any(
        x["url"] == url
        for x in c.get("/api/projects/D/schemes/scheme_manual_001/renders").json()
    )
    assert not any(x["url"] == url for x in c.get("/api/projects/D/renders").json())


def test_render_ai_503_when_ai_disabled(client, monkeypatch, tmp_path):
    c, _ = client
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key="", base_url=""))
    assert c.post("/api/projects/D/render-ai").status_code == 503


def test_scheme_render_ai_503_when_ai_disabled(client, monkeypatch, tmp_path):
    c, _ = client
    _create_scheme(c)
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key="", base_url=""))
    assert c.post("/api/projects/D/schemes/scheme_manual_001/render-ai").status_code == 503


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_ai_402_when_budget_exhausted(client, monkeypatch, tmp_path):
    c, _ = client
    monkeypatch.setattr(
        main, "_budget",
        BudgetGuard(_settings(tmp_path, max_images_per_project=0), path=str(tmp_path / "_b0.json")),
    )
    assert c.post("/api/projects/D/render-ai").status_code == 402


def test_render_ai_404_unknown_project(client):
    c, _ = client
    assert c.post("/api/projects/ZZ/render-ai").status_code == 404
