# -*- coding: utf-8 -*-
"""render-real relational_mask 档 (render-mask-b1 F002 + fix_round 1): 新档路由、降级、预算、记录字段。

fix_round 1 (F005 verifying-1 FAIL): 生成引擎 fal inpaint -> relay 整图编辑 + 羽化合成;
新增 mask 并集覆盖率上限降级。fake relay (区域估计 + relation-check VLM + 编辑) 替身。
"""
import time

import main


def _wait(c, jid, t=10.0):
    end = time.time() + t
    while time.time() < end:
        j = c.get(f"/api/ai/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job 超时")


def _upload(c, room_id="r_live", direction="v1"):
    from test_render_real_geometry import _PNG

    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": room_id or "", "direction": direction or ""},
    )
    assert r.status_code == 201, r.text
    return r.json()


_ZONES_OK = {
    "floor": [[0.0, 0.6], [0.4, 0.55], [1.0, 0.62], [1.0, 1.0], [0.0, 1.0]],
    "window_wall": [[0.4, 0.2], [1.0, 0.15], [1.0, 0.6], [0.4, 0.55]],
}
_ZONES_HUGE = {
    # 并集 100% (floor 80% + 顶部窗墙 20% 不重叠) -> 病态, 必降级
    "floor": [[0.0, 0.2], [1.0, 0.2], [1.0, 1.0], [0.0, 1.0]],
    "window_wall": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.2], [0.0, 0.2]],
}
_ZONES_LARGE_BUT_LEGIT = {
    # 并集 ~70% (floor 55% + window_wall ~15%): 合法大 mask, 不得误拦 (reverifying-1 教训)
    "floor": [[0.0, 0.45], [0.4, 0.42], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]],
    "window_wall": [[0.4, 0.2], [1.0, 0.15], [1.0, 0.5], [0.4, 0.42]],
}
_VERDICT_PASS = {"checks": [{"id": "C1", "status": "pass", "note": ""}],
                 "background_preserved": True, "background_issues": [], "summary": "ok"}


def test_relational_mask_happy_path(client_fal):
    """F002: 区域 OK -> relay 编辑 -> 羽化合成 -> diff==0 确定性验收 + mask 审计字段。"""
    c, relay, fal, _set = client_fal
    relay.chat_responses = [_ZONES_OK, _VERDICT_PASS]
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational_mask"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["strategy"] == "relational_mask"
    assert rec["rounds"] == 1
    assert rec["relation_check"]["relation_pass"] is True
    # F003 确定性背景验收: 合成保证 mask 外 diff == 0
    assert rec["background_diff"]["ok"] is True
    assert rec["background_diff"]["changed_frac"] == 0.0
    # spec §D5: mask 区域入记录供审计 + base_url (mask 存 real-base kind)
    assert rec["mask_zones"]["floor"]
    assert rec.get("base_url")
    # fix_round 1: 生成走 relay 编辑 (与 relational 同引擎), fal 不再被调
    assert len(relay.calls) == 1 and len(relay.calls[0]["images"]) == 1
    assert len(fal.calls) == 0
    assert main._budget.status()["daily_count"] == 1


def test_relational_mask_degrades_to_relational_on_bad_zones(client_fal):
    """spec §D3: 区域不健全 -> 降级为 relational 整链 + mask_degraded 记录。"""
    c, relay, fal, _set = client_fal
    relay.chat_responses = [{"window_wall": None}, _VERDICT_PASS]  # floor 缺失 -> 降级
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational_mask"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["strategy"] == "relational"  # 降级后为 relational 记录
    assert rec.get("mask_degraded")
    assert len(relay.calls) == 1  # relational 整图编辑走 relay


def test_relational_mask_coverage_over_cap_degrades(client_fal, monkeypatch):
    """fix_round 2 (F005 reverifying-1 B1): 并集 >85% 病态 -> 降级 (锁定名存实亡时不假装锁定)。

    注: 本仓 seed 家具无窗帘 -> needs 只有 floor (面积门上限 80% 凑不够病态), 故 patch
    needs 推导为含 window_wall (覆盖门是被测对象, needs 推导不是)。"""
    c, relay, fal, _set = client_fal
    monkeypatch.setattr(
        main, "_mask_needs_hints", lambda brief: ({"floor", "window_wall"}, [])
    )
    relay.chat_responses = [_ZONES_HUGE, _VERDICT_PASS]
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational_mask"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["strategy"] == "relational"
    assert "上限" in rec["mask_degraded"]


def test_relational_mask_large_but_legit_coverage_not_blocked(client_fal, monkeypatch):
    """fix_round 2: 并集 ~70% 的合法大 mask 不得误拦 (floor+窗墙是家具/窗帘的合法需求区)。"""
    c, relay, fal, _set = client_fal
    monkeypatch.setattr(
        main, "_mask_needs_hints", lambda brief: ({"floor", "window_wall"}, [])
    )
    relay.chat_responses = [_ZONES_LARGE_BUT_LEGIT, _VERDICT_PASS]
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational_mask"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["strategy"] == "relational_mask"  # 不降级, 正常走合成路径
    assert rec["background_diff"]["ok"] is True


def test_relational_mask_edit_failure_releases_budget(client_fal):
    """生成失败 -> job error + 预扣回退 (与 relational round1 失败同语义)。"""
    c, relay, fal, _set = client_fal
    relay.chat_responses = [_ZONES_OK]

    def boom(prompt, images, **kw):
        raise RuntimeError("relay down")

    relay.edit = boom
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational_mask"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "error"
    assert main._budget.status()["daily_count"] == 0
