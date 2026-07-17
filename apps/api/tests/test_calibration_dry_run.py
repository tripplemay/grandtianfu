# -*- coding: utf-8 -*-
"""calib-cure-b1 F001: 标定 dry-run 预览 — camera+重投影误差+线框投影, 不落盘, GEOM_READONLY 可用。

复用 test_render_real_geometry 的 client_fal fixture 与合成标定 payload (同一套 D 户型
tmp 沙箱, 不触真实 data/)。线框断言用响应返回的 camera 手算 Camera.project 对照,
天花板高度硬编码 2700 (实拍世界层高) —— 若实现误借 axon 压扁世界的 1450 会在此翻红。
"""

import json
from pathlib import Path

import main
import pytest
from aigc import perspective
from test_render_real_geometry import _PNG, _calib_payload, _upload_photo

_CAL_URL = "/api/projects/D/baselines/v1/photos/{pid}/calibration"


def _photo_entry(c, photo_id):
    return next(p for p in c.get("/api/projects/D/baselines/v1/photos").json() if p["id"] == photo_id)


def test_dry_run_previews_without_persisting(client_fal):
    """dry_run=1 -> 200 {ok,camera,reprojection_error,quality,wireframe}; photos.json 逐字节不变。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    photos_path = next(Path(main.DATA_DIR, "D").rglob("photos.json"))
    before = photos_path.read_bytes()
    r = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=1", json=_calib_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "K" in body["camera"] and abs(body["camera"]["focal"] - 1600) < 20
    # 合成锚点是精确投影, 重投影误差应很小。
    assert body["reprojection_error"] is not None and body["reprojection_error"] < 5.0
    # F003: quality 由 assess_calibration_quality 接管 (spec §D1)。合成锚点精确投影 ->
    # 硬门全过; fixture 相机站玄关拍客厅 (离并集 ~1950mm) 触发离房软信号 -> 非 bad 即可。
    q = body["quality"]
    assert q["ok"] is True and q["level"] in ("good", "suspect")
    assert q["metrics"]["reproj_px"] < 5.0
    assert photos_path.read_bytes() == before  # 不落盘
    assert "calibration" not in _photo_entry(c, photo["id"])


def test_dry_run_allowed_under_geom_readonly(client_fal, monkeypatch):
    """GEOM_READONLY 只拦真保存: dry_run=true 仍 200, 非 dry-run 仍 403, 均未写标定。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    monkeypatch.setattr(main, "GEOM_READONLY", True)
    r = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=true", json=_calib_payload())
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    r2 = c.post(_CAL_URL.format(pid=photo["id"]), json=_calib_payload())
    assert r2.status_code == 403  # 真保存路径行为不变
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    assert "calibration" not in _photo_entry(c, photo["id"])


def test_dry_run_wireframe_matches_camera_projection(client_fal):
    """r_master 无 merge 组: 单成员 8 点 (地面/天花各 4 角) 与 Camera.project 手算一致。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c, room_id="r_master")
    r = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=1", json=_calib_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    cam = perspective.Camera.from_dict(body["camera"])
    repo_root = Path(__file__).resolve().parents[3]
    G = json.loads((repo_root / "data/projects/D/geometry.json").read_text())
    room = next(rm for rm in G["rooms"] if rm["id"] == "r_master")
    x, y, w, h = room["rect"]
    mm = G["meta"]["mm_per_px"]
    corners = [  # NW / NE / SE / SW
        (x * mm, y * mm),
        ((x + w) * mm, y * mm),
        ((x + w) * mm, (y + h) * mm),
        (x * mm, (y + h) * mm),
    ]
    (wf,) = body["wireframe"]
    assert wf["room_id"] == "r_master"
    for z, key in ((0.0, "floor"), (2700.0, "ceiling")):  # 天花 = 实拍层高 2700, 非 axon 1450
        assert len(wf[key]) == 4
        for got, (cx, cy) in zip(wf[key], corners):
            eu, ev = cam.project(cx, cy, z)
            assert got[0] == pytest.approx(eu) and got[1] == pytest.approx(ev)


def test_dry_run_wireframe_covers_merge_group_members(client_fal):
    """r_foyer 属 m_living (含 r_live): 线框返回 2 个成员, 各 4+4 角。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c, room_id="r_foyer")
    r = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=1", json=_calib_payload())
    assert r.status_code == 200, r.text
    wf = r.json()["wireframe"]
    assert [m["room_id"] for m in wf] == ["r_foyer", "r_live"]
    for member in wf:
        assert len(member["floor"]) == 4 and len(member["ceiling"]) == 4


def test_dry_run_photo_without_room_returns_empty_wireframe(client_fal):
    c, _relay, _fal, _set = client_fal
    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
    )
    assert r.status_code == 201, r.text
    d = c.post(_CAL_URL.format(pid=r.json()["id"]) + "?dry_run=1", json=_calib_payload())
    assert d.status_code == 200, d.text
    assert d.json()["wireframe"] == []


def test_dry_run_keeps_existing_400_paths(client_fal, monkeypatch):
    """入参校验与解算失败仍走既有 400 路径, 不因 dry-run 放松。"""
    c, _relay, _fal, _set = client_fal
    photo = _upload_photo(c)
    bad = _calib_payload()
    bad["x_lines"] = bad["x_lines"][:1]  # 只 1 条线
    r = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=1", json=bad)
    assert r.status_code == 400

    def _boom(_payload):
        raise ValueError("degenerate")

    monkeypatch.setattr(main, "_calibration_camera", _boom)
    r2 = c.post(_CAL_URL.format(pid=photo["id"]) + "?dry_run=1", json=_calib_payload())
    assert r2.status_code == 400
    assert "标定失败" in r2.json()["error"]
