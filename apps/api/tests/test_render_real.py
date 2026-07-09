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
        data={"room_id": room_id, "direction": "v1"},
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
    # P0-3/P0-5: 标注了房间 -> 按房切片; 64x48 横拍照片 -> 横幅输出档。
    assert record["axon_scope"] == "room"
    assert record["size"] == "1536x1024"
    # P1-1 复现链: prompt 原文 / 底图归档 / 时间 / 引擎版本 / 照片指纹。
    assert record["prompt"].startswith("第一张图是房间的空房实拍照片")
    assert record["base_url"].startswith("/api/artifacts/D/default/real-base/")
    assert record["created_at"].endswith("Z")
    assert record["engine_version"]
    assert record["photo_sha256"] and record["photo_url"] == photo["url"]
    assert c.get(record["base_url"]).status_code == 200
    assert record["url"].startswith("/api/artifacts/D/default/real-render/")

    # 产物可取回; 历史已记入方案 renders。
    assert c.get(record["url"]).status_code == 200
    renders = c.get("/api/projects/D/schemes/default/renders").json()
    assert any(x.get("id") == record["id"] for x in renders)

    # 提示词含房间语境; 输入图顺序 = 空房照在前。
    call = provider.calls[0]
    assert "空房实拍照片" in call["prompt"]
    assert "这个房间的软装方案轴测参考图" in call["prompt"]
    assert call["size"] == "1536x1024"
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


def test_render_real_400_on_non_empty_purpose(client):
    """P0: 实拍底图必须是空房照 (purpose=empty/null); 墙面材质等非空房照直接 400。

    误把墙面材质图当结构锚点会高概率产出废图并白烧额度, 故在预扣预算前硬拦。
    """
    c, _p = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("wall.png", _PNG, "image/png")},
        data={"room_id": "r_live", "direction": "v1", "purpose": "wall_material"},
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    resp = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert resp.status_code == 400, resp.text
    assert "空房" in resp.json().get("error", "")
    # 预扣发生在用途校验之后 -> 预算未被占用。
    assert main._budget.status()["daily_count"] == 0


def test_render_real_allows_explicit_empty_purpose(client):
    """purpose 显式为 empty 的照片与缺省 (null) 一样可用于实拍底图。"""
    c, _p = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": "r_live", "direction": "v1", "purpose": "empty"},
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    # 用途校验通过 -> 进入异步生成 (200); 不因 purpose 被 400 拦下。
    resp = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert resp.status_code == 200, resp.text


def test_render_real_503_when_ai_disabled(client, monkeypatch, tmp_path):
    c, _p = client
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key=""))
    photo = _upload_photo(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert r.status_code == 503


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_real_portrait_photo_and_house_fallback(client):
    """竖拍照片选竖幅输出档 (P0-5); 未标注房间回退整宅参考 (P0-3)。"""
    c, provider = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("tall.png", _real_png((48, 96)), "image/png")},
    )
    assert r.status_code == 201, r.text
    photo = r.json()

    resp = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert resp.status_code == 200, resp.text
    job = _wait(c, resp.json()["job_id"])
    assert job["status"] == "done", job

    record = job["result"]
    assert record["size"] == "1024x1536"
    assert record["axon_scope"] == "house"
    call = provider.calls[-1]
    assert call["size"] == "1024x1536"
    assert "整套户型" in call["prompt"]
    # 参考图 letterbox 到与输出一致的画布
    from PIL import Image as _Image
    import io as _io

    with _Image.open(_io.BytesIO(call["images"][1])) as im:
        assert im.size == (1024, 1536)


def test_real_render_prompt_injects_style_soft_only():
    """P0: 方案 style_prompt 贯通第7步实拍 prompt, 但只影响可移动软装, 不动硬装/结构。"""
    G = {"rooms": [{"id": "r_live", "label": {"zh": "客厅"}, "rect": [0, 0, 400, 300]}]}
    furniture = [{"t": "sofa", "room_id": "r_live"}]
    photo = {"room_id": "r_live", "direction": "v0"}
    styled = main._real_render_prompt(
        photo, furniture, G, scope="room", style="日式原木自然风"
    )
    plain = main._real_render_prompt(photo, furniture, G, scope="room", style=None)
    # 风格词注入 styled、不在 plain (style=None 与旧字节一致)。
    assert "日式原木自然风" in styled
    assert "日式原木自然风" not in plain
    # 软/硬分层: 明确风格只影响可移动软装。
    assert "软装" in styled
    assert "不" in styled  # 含"不改变固定硬装/结构"类否定约束
    # 硬装保护语两者都在。
    assert "严格保持第一张照片的房间结构" in styled
    assert "严格保持第一张照片的房间结构" in plain


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_real_prompt_carries_scheme_style(client, monkeypatch):
    """方案 meta 的 style_prompt 端到端流到 provider 收到的实拍 prompt。"""
    c, provider = client
    photo = _upload_photo(c)
    orig = main.scheme_store.get_scheme

    def _with_style(root, house, sid):
        meta = dict(orig(root, house, sid))
        meta["style_prompt"] = "日式原木自然风"
        return meta

    monkeypatch.setattr(main.scheme_store, "get_scheme", _with_style)
    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]}
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    assert "日式原木自然风" in provider.calls[0]["prompt"]


def test_photo_direction_whitelist(client):
    """审计 P1-5: direction 只收 v0..v3 (拍摄视角 -> 轴测旋转对齐)。"""
    c, _p = client
    bad = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _real_png(), "image/png")},
        data={"direction": "north; DROP"},
    )
    assert bad.status_code == 400
    photo = _upload_photo(c)
    assert (
        c.patch(
            f"/api/projects/D/baselines/v1/photos/{photo['id']}",
            json={"direction": "X"},
        ).status_code
        == 400
    )
