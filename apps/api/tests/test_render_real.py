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
        # P1: 真实 provider 返回图尺寸可能与请求档不一致 —— fake 固定返回 1200x800 真实 PNG,
        # 让 render 记录能校验 actual_size≠requested_size。
        return ImageResult(
            data=_real_png((1200, 800)), mime="image/png",
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
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
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
    # P1: size 向后兼容 = 请求档; actual_size 读回 provider 真实返回尺寸 (fake=1200x800)。
    assert record["requested_size"] == "1536x1024"
    assert record["actual_size"] == "1200x800"
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
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": "nope"}
    )
    assert r.status_code == 404
    # 预扣已回退: 预算未被占用。
    assert main._budget.status()["daily_count"] == 0


def test_render_real_400_without_photo_id(client):
    c, _p = client
    assert (
        c.post("/api/projects/D/schemes/default/render-real", json={"strategy": "softref", }).status_code
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
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
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
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
    )
    assert resp.status_code == 200, resp.text


def test_render_real_503_when_ai_disabled(client, monkeypatch, tmp_path):
    c, _p = client
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key=""))
    photo = _upload_photo(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
    )
    assert r.status_code == 503


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_real_portrait_photo_and_house_fallback(client):
    """竖拍照片选竖幅输出档 (P0-5); 未标注房间回退整宅参考 (P0-3)。

    未标注房间/视角需显式低准确度模式 (allow_unlabeled=true) 才放行 (B2 readiness gate)。
    """
    c, provider = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("tall.png", _real_png((48, 96)), "image/png")},
    )
    assert r.status_code == 201, r.text
    photo = r.json()

    resp = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"strategy": "softref", "photo_id": photo["id"], "allow_unlabeled": True},
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
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    assert "日式原木自然风" in provider.calls[0]["prompt"]
    # P1 可复现: 本次出图的风格快照记入 record。
    assert job["result"]["style_snapshot"] == "日式原木自然风"


def test_render_real_gate_requires_room_id(client):
    """B2 readiness gate: 未标注房间时默认 400 (REAL_NOT_READY), 预算不被占用。"""
    c, _p = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"direction": "v1"},  # 有视角, 缺房间
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    resp = c.post(
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("code") == "REAL_NOT_READY"
    assert "room_id" in body.get("missing", [])
    assert main._budget.status()["daily_count"] == 0


def test_render_real_gate_requires_direction(client):
    """B2 readiness gate: 未选拍摄视角时默认 400, missing 含 direction。"""
    c, _p = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": "r_live"},  # 有房间, 缺视角
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    resp = c.post(
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": photo["id"]}
    )
    assert resp.status_code == 400, resp.text
    assert "direction" in resp.json().get("missing", [])
    assert main._budget.status()["daily_count"] == 0


def test_render_real_gate_allows_low_accuracy_bypass(client):
    """allow_unlabeled=true 显式降级低准确度模式: 未标注也放行 (返回 job)。"""
    c, _p = client
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    resp = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"strategy": "softref", "photo_id": photo["id"], "allow_unlabeled": True},
    )
    assert resp.status_code == 200, resp.text
    assert "job_id" in resp.json()


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="需 rsvg-convert")
def test_render_real_low_accuracy_recorded(client):
    """低准确度模式生成的记录带 low_accuracy=true (溯源); 完整标注则不带该键。"""
    c, _p = client
    # 未标注 -> 低准确度
    bare = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("bare.png", _PNG, "image/png")},
    ).json()
    resp = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"strategy": "softref", "photo_id": bare["id"], "allow_unlabeled": True},
    )
    assert resp.status_code == 200, resp.text
    rec = _wait(c, resp.json()["job_id"])["result"]
    assert rec["low_accuracy"] is True

    # 完整标注 -> 不带 low_accuracy 键 (字节兼容既有记录)。
    labeled = _upload_photo(c)
    resp2 = c.post(
        "/api/projects/D/schemes/default/render-real", json={"strategy": "softref", "photo_id": labeled["id"]}
    )
    assert resp2.status_code == 200, resp2.text
    rec2 = _wait(c, resp2.json()["job_id"])["result"]
    assert "low_accuracy" not in rec2


def test_real_render_prompt_injects_brief():
    """B3: 结构化 Brief 编译片段拼进实拍 prompt; brief=None 时与旧字节一致。"""
    G = {"rooms": [{"id": "r_live", "label": {"zh": "客厅"}, "rect": [0, 0, 400, 300]}]}
    furniture = [{"t": "sofa", "room_id": "r_live"}]
    photo = {"room_id": "r_live", "direction": "v0"}
    with_brief = main._real_render_prompt(
        photo, furniture, G, scope="room",
        brief={"style_direction": "modern", "banned_colors": ["neon"]},
    )
    plain = main._real_render_prompt(photo, furniture, G, scope="room", brief=None)
    assert "Design brief — style direction: modern" in with_brief
    assert "avoid colors: neon" in with_brief
    assert "Design brief" not in plain
    # 硬装保护语两者都在 (brief 只追加, 不改既有结构)。
    assert "严格保持第一张照片的房间结构" in with_brief
    assert "严格保持第一张照片的房间结构" in plain


def test_real_render_placement_tv_sofa_anchor():
    """Phase 1: 客厅电视柜贴最近实墙、沙发正对电视柜 —— 不再按三等分把沙发误说成贴南墙。

    真实 D 布局 (r_live 720x765): 电视柜 media 贴东墙 (dx663), 沙发在西南 (dx225,dy518)
    离南墙最近。旧三等分把沙发中心判 south -> "画面近侧" (南=景观区落地窗开口), 诱导 AI 贴窗;
    电视柜被判 south-east 角而非贴东墙。新逻辑: 电视柜取最近实墙 (东), 沙发只给关系锚。
    """
    G = {"rooms": [{"id": "r_live", "label": {"zh": "客厅"}, "rect": [0, 0, 720, 765]}]}
    furniture = [
        {"t": "media", "room_id": "r_live", "dx": 663, "dy": 550, "w": 44, "h": 200},
        {"t": "sofa", "room_id": "r_live", "dx": 225, "dy": 518, "w": 96, "h": 232},
    ]
    photo = {"room_id": "r_live", "direction": "v0"}
    p = main._real_render_prompt(photo, furniture, G, scope="room")
    # 电视柜: 贴最近实墙 (东), 构成电视墙; v0 视角 east -> 画面右侧。
    assert "电视墙" in p
    assert "画面右侧墙" in p
    # 沙发: 关系锚 "正对电视柜", 而非三等分靠墙短语。
    assert "正对电视柜" in p


def test_real_render_placement_ignores_unreliable_orient():
    """Phase 1: 落位不依赖 legacy 数据不可信的 orient —— 同布局下 orient 变化不改落位话术。"""
    G = {"rooms": [{"id": "r_live", "label": {"zh": "客厅"}, "rect": [0, 0, 720, 765]}]}
    media = {"t": "media", "room_id": "r_live", "dx": 663, "dy": 550, "w": 44, "h": 200}
    sofa = {"t": "sofa", "room_id": "r_live", "dx": 225, "dy": 518, "w": 96, "h": 232}
    photo = {"room_id": "r_live", "direction": "v0"}
    p_none = main._real_render_prompt(photo, [media, sofa], G, scope="room")
    p_e = main._real_render_prompt(photo, [media, {**sofa, "orient": "E"}], G, scope="room")
    p_s = main._real_render_prompt(photo, [media, {**sofa, "orient": "S"}], G, scope="room")
    assert p_none == p_e == p_s


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
