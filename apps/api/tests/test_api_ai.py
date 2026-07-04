# -*- coding: utf-8 -*-
"""AI 端点集成 (TestClient): status / artifacts 服务+404 / 上传 (产物指向 tmp, 不污染仓库)。"""
import importlib

import pytest
from fastapi.testclient import TestClient

import main
from aigc.artifacts import ArtifactStore
from aigc.budget import BudgetGuard
from aigc.config import Settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 产物/上传/预算 全部重指向 tmp, 从结构上杜绝测试写入仓库 artifacts/data (红线)。
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(str(tmp_path / "art")))
    monkeypatch.setattr(main, "_uploads", ArtifactStore(str(tmp_path / "up")))
    monkeypatch.setattr(
        main, "_budget", BudgetGuard(main._settings, path=str(tmp_path / "_budget.json"))
    )
    return TestClient(main.app)


def test_ai_disabled_does_not_break_core(client, monkeypatch):
    """凭据缺失 -> AI 灰显 (enabled=False), 但既有只读端点照常 (红线②)。"""
    disabled = Settings(
        provider="openai", base_url="", api_key="", model="gpt-image-2", proxy=None,
        request_timeout_s=300.0, artifacts_dir="/tmp", uploads_dir="/tmp",
        max_images_per_project=1, daily_image_cap=1,
    )
    monkeypatch.setattr(main, "_settings", disabled)
    assert client.get("/api/ai/status").json()["enabled"] is False
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/projects/D/geometry").status_code == 200


def test_ai_status_shape(client):
    r = client.get("/api/ai/status")
    assert r.status_code == 200
    body = r.json()
    assert set(["enabled", "provider", "model", "budget"]).issubset(body)


def test_artifact_404_and_serve(client):
    assert client.get("/api/artifacts/D/render/missing.png").status_code == 404
    rel = main._artifacts.save(b"\x89PNG\r\n\x1a\n----", project_id="D", kind="render", ext="png")
    r = client.get(f"/api/artifacts/{rel}")
    assert r.status_code == 200
    assert "immutable" in r.headers.get("cache-control", "")


def test_served_images_have_correct_content_type(client):
    """回归: webp 缩略图曾被 FileResponse 默认成 application/octet-stream, 叠加 nosniff 后
    浏览器拒渲染 -> 所有缩略图空白。显式 media_type 后 webp/jpeg/png 均正确, 浏览器可显示。"""
    # 产物 (AI 效果图缩略图) webp
    rel_webp = main._artifacts.save(
        b"RIFF\x00\x00\x00\x00WEBP", project_id="D", kind="real-thumb", ext="webp"
    )
    rw = client.get(f"/api/artifacts/{rel_webp}")
    assert rw.status_code == 200
    assert rw.headers["content-type"] == "image/webp"
    assert rw.headers.get("x-content-type-options") == "nosniff"  # 安全头保留
    # 上传 (空房照缩略图) webp + 原图 jpg
    up_webp = main._uploads.save(
        b"RIFF\x00\x00\x00\x00WEBP", project_id="D", kind="empty-thumb", ext="webp"
    )
    assert client.get(f"/api/uploads/{up_webp}").headers["content-type"] == "image/webp"
    up_jpg = main._uploads.save(b"\xff\xd8\xff----", project_id="D", kind="empty", ext="jpg")
    assert client.get(f"/api/uploads/{up_jpg}").headers["content-type"] == "image/jpeg"


def test_artifact_traversal_404(client):
    assert client.get("/api/artifacts/../../etc/passwd").status_code in (404, 400)


def test_job_404(client):
    assert client.get("/api/ai/jobs/deadbeef").status_code == 404


@pytest.mark.skipif(
    importlib.util.find_spec("multipart") is None,
    reason="python-multipart 未安装",
)
def test_bare_upload_endpoint_is_retired(client):
    """审计 P2-2: 裸 POST /uploads 落盘不登记即孤儿, 已退役 —— 照片一律走 photos 端点。"""
    import io as _io

    from PIL import Image as _Image

    buf = _io.BytesIO()
    _Image.new("RGB", (32, 24), (5, 5, 5)).save(buf, format="PNG")
    r = client.post(
        "/api/projects/D/uploads",
        files={"file": ("room.png", buf.getvalue(), "image/png")},
    )
    assert r.status_code in (404, 405)


@pytest.mark.skipif(
    importlib.util.find_spec("multipart") is None,
    reason="python-multipart 未安装",
)
def test_photos_upload_rejects_non_image(client):
    r = client.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 415
