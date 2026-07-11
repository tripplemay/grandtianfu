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


def test_calibration_stores_binding_and_reprojection_error(client_fal):
    """P0-5: 标定落 binding 指纹 (room_id/room_rect_hash/image_w/h/来源版本) + reprojection_error。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)  # room_id=r_live
    r = c.post(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}/calibration",
        json=_calib_payload(),
    )
    assert r.status_code == 200, r.text
    cal = r.json()["calibration"]
    b = cal["binding"]
    assert b["room_id"] == "r_live"
    assert b["room_rect_hash"] and b["geometry_hash"]
    assert b["created_from_baseline_version_id"] == "v1"
    # 合成锚点是精确投影, 反解相机重投影误差应很小。
    assert cal["reprojection_error"] is not None and cal["reprojection_error"] < 5.0


def test_render_real_blocks_stale_calibration_after_room_change(client_fal, monkeypatch):
    """P0-5: 标定后把照片房间改掉 -> 标定失效 -> render-real 409 STALE_CALIBRATION, provider 未被调。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _calibrated_photo(c)  # 标定时 room_id=r_live, binding.room_id=r_live
    # 改照片房间 -> 标定绑定的房间与现值不符 = stale。
    pr = c.patch(
        f"/api/projects/D/baselines/v1/photos/{photo['id']}",
        json={"room_id": "r_master"},
    )
    assert pr.status_code == 200, pr.text

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "STALE_CALIBRATION"
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_list_photos_flags_stale_calibration(client_fal):
    """P0-5: GET photos 逐张附 calibration_stale 供前端主动展示第三态。"""
    c, _relay, _fal, _set = client_fal
    photo = _calibrated_photo(c)
    # 新标定, fresh。
    lst = c.get("/api/projects/D/baselines/v1/photos").json()
    entry = next(p for p in lst if p["id"] == photo["id"])
    assert entry.get("calibration_stale") is False
    # 改房间 -> stale。
    c.patch(f"/api/projects/D/baselines/v1/photos/{photo['id']}", json={"room_id": "r_master"})
    lst2 = c.get("/api/projects/D/baselines/v1/photos").json()
    entry2 = next(p for p in lst2 if p["id"] == photo["id"])
    assert entry2.get("calibration_stale") is True


def test_calibration_stale_covers_merge_group_siblings():
    """P0-5 审查修复: room_rect_hash 纳入整个 merge 组 —— 编辑同组兄弟房也判 stale, 无关房不误判。"""
    import copy

    from floorplan_core import geometry

    G = geometry.load("data/projects/D/geometry.json")
    photo = {"id": "p1", "room_id": "r_live", "width": 2048, "height": 1536}
    cal = {
        "camera": {},
        "binding": {
            **main._calibration_binding(G, "r_live", photo),
            "created_from_baseline_version_id": "v1",
        },
    }
    assert main._calibration_stale_reason(cal, G, photo) is None  # 同几何 fresh
    # 编辑 merge 兄弟房 r_foyer (与 r_live 同属 m_living) -> stale。
    g_sib = copy.deepcopy(G)
    next(r for r in g_sib["rooms"] if r["id"] == "r_foyer")["rect"][0] += 30
    assert main._calibration_stale_reason(cal, g_sib, photo) is not None
    # 编辑无关房 r_master -> 仍 fresh (不过度失效)。
    g_unrel = copy.deepcopy(G)
    next(r for r in g_unrel["rooms"] if r["id"] == "r_master")["rect"][0] += 30
    assert main._calibration_stale_reason(cal, g_unrel, photo) is None


def test_geometry_lock_prompt_distinguishes_near_and_partial():
    """P0-5 审查修复: near (贴镜头前景) 与 partial (画幅裁切) 用不同话术, 不混用。"""
    near_prompt = main._geometry_lock_prompt(
        [{"color": "green", "t": "media", "count": 1, "near": True}], [], None
    )
    assert "near foreground" in near_prompt and "do not shrink it into the background" in near_prompt
    assert "hidden portion" not in near_prompt  # near 不该说"被裁切/勿补全"
    partial_prompt = main._geometry_lock_prompt(
        [{"color": "blue", "t": "sofa", "count": 1, "partial": True}], [], None
    )
    assert "partly outside the frame" in partial_prompt and "hidden portion" in partial_prompt
    assert "near foreground" not in partial_prompt  # partial 不该说"贴镜头前景"


def test_render_real_legacy_calibration_without_binding_is_fresh(client_fal, monkeypatch):
    """P0-5 兼容: 无 binding 指纹的历史标定 (线上存量) 不判 stale, 照常出图。"""
    c, relay, _fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _upload_photo(c)
    # 直接落一个无 binding 的旧式标定 (绕开端点的 binding 注入)。
    from aigc.perspective import calibrate

    cam = calibrate(
        [((p[0][0], p[0][1]), (p[1][0], p[1][1])) for p in _calib_payload()["x_lines"]],
        [((p[0][0], p[0][1]), (p[1][0], p[1][1])) for p in _calib_payload()["y_lines"]],
        [((a["world"][0], a["world"][1], a["world"][2]), (a["px"][0], a["px"][1])) for a in _calib_payload()["anchors"]],
        img_wh=(2048, 1536),
    )
    import baselines as _bl

    _bl.set_photo_calibration(
        main.DATA_DIR,
        "D",
        "v1",
        photo["id"],
        {"x_lines": _calib_payload()["x_lines"], "y_lines": _calib_payload()["y_lines"],
         "anchors": _calib_payload()["anchors"], "img_wh": [2048, 1536], "camera": cam.to_dict()},
    )
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job  # 无 binding = 兼容当 fresh, 照常出图


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


def _stub_accept(monkeypatch, verdicts):
    """按次序弹出 P4 验收结论 (main.acceptance.evaluate_geometry_lock 替身)。"""
    seq = list(verdicts)
    calls = []

    def fake(empty_png, out_png, **kw):
        calls.append(kw)
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr(main.acceptance, "evaluate_geometry_lock", fake)
    return calls


def _save_bad_layout(c):
    """把 default 方案家具换成"悬空于客厅中央的酒柜" (场景校验过但布局 lint 不过)。"""
    r = c.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[{"t": "wine_cabinet", "w": 60, "h": 40, "room_id": "r_live", "dx": 350, "dy": 350}],
    )
    assert r.status_code == 200, r.text


def test_render_real_layout_gate_blocks_floating_wall_unit(client_fal, monkeypatch):
    """布局 lint 门禁: 酒柜悬空 -> 400 LAYOUT_NOT_READY, provider 未被调 (预扣已退)。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _calibrated_photo(c)
    _save_bad_layout(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "LAYOUT_NOT_READY"
    codes = [i["code"] for i in body["layout_lint"]["issues"]]
    assert "LAYOUT_WALL_UNIT_FLOATING" in codes
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_render_real_layout_gate_degradable_with_allow_flag(client_fal, monkeypatch):
    """布局 lint 门禁可降级: allow_layout_issues=true -> 照常生成, 记录打 layout_issues_overridden。"""
    c, relay, _fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _calibrated_photo(c)
    _save_bad_layout(c)

    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "allow_layout_issues": True},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["method"] == "geometry-lock"
    assert rec.get("layout_issues_overridden") is True
    assert len(relay.calls) == 1


def test_render_real_layout_gate_scoped_to_photo_room(client_fal, monkeypatch):
    """门禁作用域=照片那间房: r_live 干净 (photo 在 r_live), 另一间房 r_master 的悬空酒柜
    不牵连误拦 -> 照常生成。"""
    c, relay, _fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _calibrated_photo(c)  # 默认 room_id=r_live
    # r_live 放干净沙发 (可投影, 无 lint 问题); r_master 放悬空酒柜 (脏, 但不在 photo 作用域)。
    r = c.post(
        "/api/projects/D/schemes/default/save-furniture",
        json=[
            {"t": "sofa", "w": 210, "h": 90, "room_id": "r_live", "dx": 60, "dy": 60},
            {"t": "wine_cabinet", "w": 60, "h": 40, "room_id": "r_master", "dx": 250, "dy": 180},
        ],
    )
    assert r.status_code == 200, r.text
    resp = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert resp.status_code == 200, resp.text
    job = _wait(c, resp.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"].get("layout_issues_overridden") is None  # 未越过 (作用域内干净)
    assert len(relay.calls) == 1


def test_scene_endpoint_exposes_layout_lint(client_fal):
    """GET scene 透出 layout_lint 信封: 干净布局 ok=True; 悬空酒柜 ok=False 含 issue。"""
    c, _relay, _fal, _set = client_fal
    clean = c.get("/api/projects/D/schemes/default/scene")
    assert clean.status_code == 200
    assert clean.json()["layout_lint"]["ok"] is True

    _save_bad_layout(c)
    bad = c.get("/api/projects/D/schemes/default/scene")
    lint_res = bad.json()["layout_lint"]
    assert lint_res["ok"] is False
    assert any(i["code"] == "LAYOUT_WALL_UNIT_FLOATING" for i in lint_res["issues"])


def test_render_real_geometry_lock_default_relay_backend(client_fal, monkeypatch):
    """默认后端 relay: 几何锁定走 gpt-image-2 双图编辑 (A/B 胜出), fal 不被调。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
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
    assert rec["auto_check"] == {"ok": True, "score": 1.0, "fail_reasons": [], "attempts": 1}
    assert c.get(rec["url"]).status_code == 200


def test_render_real_geometry_lock_fal_backend(client_fal, monkeypatch):
    """GEOMETRY_EDIT_BACKEND=fal: 同一引导走 nano-banana, relay 不被调。"""
    c, relay, fal, set_settings = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
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


def test_render_real_auto_check_retry_then_pass(client_fal, monkeypatch):
    """P4: 首图验收不过 -> 带修正指令重试 -> 二图过关; 记录 attempts=2。"""
    c, relay, _fal, _set = client_fal
    bad = {"ok": False, "score": 0.4, "fail_reasons": ["sofa 盒区未见家具 (盒内改动 3)"], "checks": {}}
    good = {"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}
    _stub_accept(monkeypatch, [bad, good])
    photo = _calibrated_photo(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert len(relay.calls) == 2
    # 重试 prompt 追加了针对失败项的修正指令
    assert "EVERY box" in relay.calls[1]["prompt"]
    assert rec["auto_check"]["ok"] is True
    assert rec["auto_check"]["attempts"] == 2


def test_render_real_auto_check_soft_gate_keeps_best(client_fal, monkeypatch):
    """P4 软门: 重试用尽仍不过 -> 交付得分最高的一张, auto_check.ok=false 不报错。"""
    c, relay, _fal, _set = client_fal
    worse = {"ok": False, "score": 0.3, "fail_reasons": ["盒区外出现新结构 (新边缘坏块 9/100)"], "checks": {}}
    bad = {"ok": False, "score": 0.6, "fail_reasons": ["sofa 盒区未见家具 (盒内改动 3)"], "checks": {}}
    _stub_accept(monkeypatch, [worse, bad])
    photo = _calibrated_photo(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job  # 软门: 不过关也交付
    rec = job["result"]
    assert len(relay.calls) == 2  # 默认 max_retries=1
    assert rec["auto_check"]["ok"] is False
    assert rec["auto_check"]["score"] == 0.6  # 择优保留分高的第二张
    assert rec["auto_check"]["attempts"] == 2


def test_render_real_auto_check_disabled(client_fal, monkeypatch):
    """GEOMETRY_ACCEPT=0: 不验收不重试, auto_check 标记 skipped。"""
    c, relay, _fal, set_settings = client_fal
    set_settings(geometry_accept=False)
    called = _stub_accept(monkeypatch, [{"ok": False}])  # 若被调用则会失败重试
    photo = _calibrated_photo(c)

    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert len(relay.calls) == 1
    assert called == []  # 评审器未被调用
    assert rec["auto_check"] == {"ok": True, "skipped": True, "attempts": 1}


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


def test_render_real_backend_override_relay_beats_fal_setting(client_fal, monkeypatch):
    """请求级 backend=relay 覆盖 settings 级 fal (换后端重试): relay 被调, fal 不被调。"""
    c, relay, fal, set_settings = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    set_settings(geometry_edit_backend="fal")
    photo = _calibrated_photo(c)

    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "backend": "relay"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["method"] == "geometry-lock"
    assert rec["edit_backend"] == "relay"
    assert rec["model"] == "gpt-image-2"
    assert len(relay.calls) == 1
    assert len(fal.calls) == 0


def test_render_real_backend_override_fal(client_fal, monkeypatch):
    """请求级 backend=fal 覆盖 settings 级默认 relay: nano-banana 被调。"""
    c, relay, fal, _set = client_fal
    _stub_accept(monkeypatch, [{"ok": True, "score": 1.0, "fail_reasons": [], "checks": {}}])
    photo = _calibrated_photo(c)

    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "backend": "fal"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["edit_backend"] == "fal"
    assert rec["model"] == "fal-ai/nano-banana/edit"
    assert len(fal.calls) == 1
    assert len(relay.calls) == 0


def test_render_real_backend_invalid_value_400(client_fal):
    """backend 非法值 -> 400, 不产生任何 provider 调用。"""
    c, relay, fal, _set = client_fal
    photo = _calibrated_photo(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "backend": "nano"},
    )
    assert r.status_code == 400
    assert "backend" in r.json()["error"]
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_render_real_backend_fal_explicit_without_key_400(client_fal):
    """显式指定 fal 但缺 FAL_KEY -> 400 明确报错, 不得静默回退别的路径 (误导用户)。"""
    c, relay, fal, set_settings = client_fal
    set_settings(fal_key="")
    photo = _calibrated_photo(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "backend": "fal"},
    )
    assert r.status_code == 400
    assert "FAL_KEY" in r.json()["error"]
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_render_real_backend_requires_calibration_400(client_fal):
    """未标定照片 + 显式 backend -> 400 (换后端仅对几何锁定路径有意义)。"""
    c, relay, fal, _set = client_fal
    photo = _upload_photo(c)  # 未标定
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "backend": "relay"},
    )
    assert r.status_code == 400
    assert "标定" in r.json()["error"]
    assert len(relay.calls) == 0 and len(fal.calls) == 0


def test_renders_list_exposes_auto_check_and_edit_backend(client_fal, monkeypatch):
    """列表契约: 瘦身列表 (detail 缺省) 保留 auto_check/edit_backend/method, 剥重键。

    前端失败折叠/换后端重试按钮都靠这三个字段, 此契约破坏 = UI 静默失效。
    """
    c, _relay, _fal, _set = client_fal
    _stub_accept(
        monkeypatch,
        [{"ok": False, "score": 0.7, "fail_reasons": ["media 盒区未见家具 (盒内改动 7)"], "checks": {}}],
    )
    photo = _calibrated_photo(c)
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job

    lst = c.get("/api/projects/D/schemes/default/renders")
    assert lst.status_code == 200
    rec = lst.json()[0]
    assert rec["method"] == "geometry-lock"
    assert rec["edit_backend"] == "relay"
    assert rec["auto_check"]["ok"] is False
    assert rec["auto_check"]["fail_reasons"] == ["media 盒区未见家具 (盒内改动 7)"]
    # 重试用尽仍不过: attempts = 1 + max_retries (默认 1)
    assert rec["auto_check"]["attempts"] == 2
    for heavy in ("scene_manifest", "usage", "prompt"):
        assert heavy not in rec  # 瘦身仍生效
