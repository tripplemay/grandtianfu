# -*- coding: utf-8 -*-
"""路线A 几何锁定实拍 (P2b+P3): 透视标定端点 + render-real 走 fal 彩盒标注编辑路径。

无需 rsvg (几何锁定不渲轴测, 用 perspective annotate_boxes)。fal provider 被 mock。
"""

import io
import shutil
import time
from pathlib import Path

import main
import numpy as np
import pytest
from aigc.artifacts import ArtifactStore
from aigc.budget import BudgetGuard
from aigc.config import Settings
from aigc.providers import ImageResult
from aigc.records import RenderLog
from fastapi.testclient import TestClient
from PIL import Image


def _png(size=(2048, 1536)):
    buf = io.BytesIO()
    Image.new("RGB", size, (180, 170, 150)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png((64, 48))


def _settings(tmp_path, **over):
    base = dict(
        provider="openai",
        base_url="https://relay/v1",
        api_key="sk-test",
        model="gpt-image-2",
        proxy=None,
        request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"),
        uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5,
        daily_image_cap=10,
        fal_key="fal-x",
    )
    base.update(over)
    return Settings(**base)


class _FakeFal:
    def __init__(self):
        self.calls = []

    def edit(self, prompt, images, *, model=None, extra=None):
        self.calls.append({"prompt": prompt, "images": images, "model": model, "extra": extra})
        return ImageResult(
            data=_png((1200, 800)),
            mime="image/png",
            usage={"width": 1200, "height": 800},
            model="fal-ai/nano-banana/edit",
        )


class _FakeRelay:
    """OpenAIImageProvider 替身 (relay 后端: gpt-image-2 双图编辑)。"""

    def __init__(self):
        self.calls = []

    def edit(self, prompt, images, *, size="1536x1024", model=None):
        self.calls.append({"prompt": prompt, "images": images, "size": size, "model": model})
        return ImageResult(
            data=_png((1448, 1086)),
            mime="image/png",
            usage={"total_tokens": 4700},
            model=model or "gpt-image-2",
        )


@pytest.fixture
def client_fal(tmp_path, monkeypatch):
    """返回 (TestClient, relay替身, fal替身, settings覆写函数)。默认后端 relay。"""
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    shutil.copyfile(repo_root / "data/projects/D/geometry.json", project / "geometry.json")
    shutil.copyfile(repo_root / "data/projects/D/furniture.json", project / "furniture.json")
    s = _settings(tmp_path)
    relay = _FakeRelay()
    fal = _FakeFal()
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    monkeypatch.setattr(main, "_settings", s)
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(s.artifacts_dir))
    monkeypatch.setattr(main, "_uploads", ArtifactStore(s.uploads_dir))
    monkeypatch.setattr(main, "_budget", BudgetGuard(s, path=str(tmp_path / "_b.json")))
    monkeypatch.setattr(main, "_renders", RenderLog(s.artifacts_dir))
    monkeypatch.setattr(main, "get_provider", lambda _s: relay)
    monkeypatch.setattr(main, "get_fal_provider", lambda _s: fal)

    def set_settings(**over):
        s2 = _settings(tmp_path, **over)
        monkeypatch.setattr(main, "_settings", s2)
        return s2

    return TestClient(main.app), relay, fal, set_settings


def _upload_photo(c, room_id="r_live"):
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": room_id, "direction": "v1"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _calib_payload(W=2048, H=1536, f=1600.0):
    """合成相机投影生成合法墙线 + 锚点 (端点会据此反解相机)。"""
    cx, cy = W / 2, H / 2
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    eye = np.array([3000.0, 3000.0, 1450.0])
    fwd = np.array([10000.0, 12000.0, 0.0]) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    down /= np.linalg.norm(down)
    R = np.vstack([right, down, fwd])
    t = -R @ eye

    def P(x, y, z):
        uv = K @ (R @ np.array([x, y, z], float) + t)
        return [float(uv[0] / uv[2]), float(uv[1] / uv[2])]

    return {
        "x_lines": [[P(5000, 14000, 0), P(12000, 14000, 0)], [P(5000, 9000, 0), P(12000, 9000, 0)]],
        "y_lines": [[P(12000, 5000, 0), P(12000, 14000, 0)], [P(8000, 5000, 0), P(8000, 14000, 0)]],
        "anchors": [
            {"world": [12000, 14000, 0], "px": P(12000, 14000, 0)},
            {"world": [5000, 14000, 0], "px": P(5000, 14000, 0)},
        ],
        "img_wh": [W, H],
    }


def _wait(c, jid, t=10.0):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/ai/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job 超时")


def test_calibration_endpoint_stores_camera(client_fal):
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    r = c.post(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration",
        json=_calib_payload(),
    )
    assert r.status_code == 200, r.text
    cal = r.json()["calibration"]
    assert "camera" in cal and "K" in cal["camera"]
    assert abs(cal["camera"]["focal"] - 1600) < 20  # 焦距反解


def test_calibration_rejects_too_few_lines(client_fal):
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    bad = _calib_payload()
    bad["x_lines"] = bad["x_lines"][:1]  # 只 1 条线
    r = c.post(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration", json=bad)
    assert r.status_code == 400


def _calibrated_photo(c):
    photo = _upload_photo(c)
    assert (
        c.post(
            f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration", json=_calib_payload()
        ).status_code
        == 200
    )
    return photo


def test_render_real_geometry_lock_default_relay_backend(client_fal):
    """默认后端 relay: 几何锁定走 gpt-image-2 双图编辑 (A/B 胜出), fal 不被调。"""
    c, relay, fal, _set = client_fal
    photo = _calibrated_photo(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["mode"] == "real-photo"
    assert rec["method"] == "geometry-lock"
    assert rec["form_guidance"] == "anno-box-edit"  # 形体提质: 彩盒标注+指令编辑
    assert rec["model"] == "gpt-image-2"
    assert rec["furniture_locked"] >= 1
    assert rec["guide_url"].startswith("/api/artifacts/D/default/real-base/")
    assert len(fal.calls) == 0
    assert len(relay.calls) == 1
    call = relay.calls[0]
    images = call["images"]
    assert len(images) == 2  # [空房照, 彩盒标注图]
    assert images[1][:8] == b"\x89PNG\r\n\x1a\n"  # 标注图是 PNG
    assert call["model"] == "gpt-image-2"
    # 请求档按照片纵横比选 (2048x1536 -> 4:3 档), 防 relay 重取景
    w, h = (int(x) for x in call["size"].split("x"))
    assert abs(w / h - 2048 / 1536) < 0.2
    prompt = call["prompt"].lower()
    assert "image 2" in prompt and "box =" in prompt  # 双图指令 + 颜色映射
    assert c.get(rec["url"]).status_code == 200


def test_render_real_geometry_lock_fal_backend(client_fal):
    """GEOMETRY_EDIT_BACKEND=fal: 同一引导走 nano-banana, relay 不被调。"""
    c, relay, fal, set_settings = client_fal
    set_settings(geometry_edit_backend="fal")
    photo = _calibrated_photo(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["method"] == "geometry-lock"
    assert rec["model"] == "fal-ai/nano-banana/edit"
    assert len(relay.calls) == 0
    assert len(fal.calls) == 1
    assert len(fal.calls[0]["images"]) == 2


def test_render_real_geometry_lock_fal_backend_without_key_falls_back(client_fal):
    """后端配 fal 但缺 FAL_KEY -> 不走几何锁定 (回退轴测软参考路径), 两替身都不被调到几何锁定。"""
    c, _relay, fal, set_settings = client_fal
    set_settings(geometry_edit_backend="fal", fal_key="")
    photo = _calibrated_photo(c)
    c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert len(fal.calls) == 0  # 几何锁定被跳过 (fal 未配)


def test_render_real_no_calibration_falls_back(client_fal, monkeypatch):
    """无标定 -> 不走几何锁定; 落到轴测软参考兼容路径 (需 rsvg)。"""
    c, _relay, fal, _set = client_fal
    photo = _upload_photo(c)  # 未标定
    # 未标注 direction 之外 room_id 有 -> readiness gate 只缺 direction? 这里 direction=v1 已给。
    # 无 calibration -> geometry-lock 分支跳过; 走旧路径 (需 rsvg 渲轴测)。仅验证 fal 未被调。
    c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    # 旧路径可能因无 rsvg 500 或成功; 关键: 未走 fal 几何锁定。
    assert len(fal.calls) == 0
