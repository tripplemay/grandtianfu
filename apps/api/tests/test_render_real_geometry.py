# -*- coding: utf-8 -*-
"""路线A 几何锁定实拍 (P2b+P3): 透视标定端点 + render-real 走 fal footprint-mask 路径。

无需 rsvg (几何锁定不渲轴测, 用 perspective footprint mask)。fal provider 被 mock。
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

    def inpaint(
        self, prompt, init_png, mask_png, *, controlnets=None, size=None, strength=0.9, steps=30
    ):
        self.calls.append({"prompt": prompt, "init": init_png, "mask": mask_png, "size": size})
        return ImageResult(
            data=_png((1200, 800)),
            mime="image/png",
            usage={"width": 1200, "height": 800},
            model="fal-flux-general",
        )


@pytest.fixture
def client_fal(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    shutil.copyfile(repo_root / "data/projects/D/geometry.json", project / "geometry.json")
    shutil.copyfile(repo_root / "data/projects/D/furniture.json", project / "furniture.json")
    s = _settings(tmp_path)
    fal = _FakeFal()
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    monkeypatch.setattr(main, "_settings", s)
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(s.artifacts_dir))
    monkeypatch.setattr(main, "_uploads", ArtifactStore(s.uploads_dir))
    monkeypatch.setattr(main, "_budget", BudgetGuard(s, path=str(tmp_path / "_b.json")))
    monkeypatch.setattr(main, "_renders", RenderLog(s.artifacts_dir))
    monkeypatch.setattr(main, "get_fal_provider", lambda _s: fal)
    return TestClient(main.app), fal


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
    c, _fal = client_fal
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
    c, _fal = client_fal
    photo = _upload_photo(c)
    bad = _calib_payload()
    bad["x_lines"] = bad["x_lines"][:1]  # 只 1 条线
    r = c.post(f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration", json=bad)
    assert r.status_code == 400


def test_render_real_geometry_lock_uses_fal(client_fal):
    c, fal = client_fal
    photo = _upload_photo(c)
    assert (
        c.post(
            f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration", json=_calib_payload()
        ).status_code
        == 200
    )

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["mode"] == "real-photo"
    assert rec["method"] == "geometry-lock"  # 走 fal 几何锁定, 非 gpt-image-2
    assert rec["furniture_locked"] >= 1
    assert rec["mask_url"].startswith("/api/artifacts/D/default/real-base/")
    # fal.inpaint 被调, 收到 init + mask
    assert len(fal.calls) == 1
    assert fal.calls[0]["mask"][:8] == b"\x89PNG\r\n\x1a\n"  # mask 是 PNG
    assert "masked" in fal.calls[0]["prompt"].lower()
    assert c.get(rec["url"]).status_code == 200


def test_render_real_no_calibration_falls_back(client_fal, monkeypatch):
    """无标定 -> 不走几何锁定 (fal 不被调); 落到 gpt-image-2 兼容路径的 readiness gate。"""
    c, fal = client_fal
    photo = _upload_photo(c)  # 未标定
    # 未标注 direction 之外 room_id 有 -> readiness gate 只缺 direction? 这里 direction=v1 已给。
    # 无 calibration -> geometry-lock 分支跳过; 走旧路径 (需 rsvg 渲轴测)。仅验证 fal 未被调。
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    # 旧路径可能因无 rsvg 500 或成功; 关键: 未走 fal 几何锁定。
    assert len(fal.calls) == 0
