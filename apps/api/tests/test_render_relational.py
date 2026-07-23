# -*- coding: utf-8 -*-
"""render-real relational 档 (render-relation-b1 F002/F003): 三档分派、约束简报、VLM 闭环。

fake relay 替身 (client_fal fixture); VLM 应答经 relay.chat_responses 按序注入。
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


def _verdict(checks, bg=True):
    return {"checks": checks, "background_preserved": bg, "background_issues": [], "summary": "s"}


_PASS_ALL = _verdict([{"id": "C1", "status": "pass", "note": ""}])
_FAIL_ONE = _verdict(
    [
        {"id": "C1", "status": "fail", "note": "沙发没贴墙"},
        {"id": "C2", "status": "pass", "note": ""},
    ]
)
_FAIL_WORSE = _verdict(
    [{"id": "C1", "status": "fail", "note": "a"}, {"id": "C2", "status": "fail", "note": "b"}]
)


def test_relational_is_default_strategy(client_fal):
    """F002: 不显式给 strategy -> relational 主路径 (单图编辑 + 验收入记录)。"""
    c, relay, _fal, _set = client_fal
    photo = _upload(c)
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    assert job["status"] == "done", job
    rec = job["result"]
    assert rec["strategy"] == "relational"
    assert rec["relation_check"]["relation_pass"] is True
    assert rec["placement_brief"]["constraints"]
    assert rec["rounds"] == 1  # 默认 VLM 全过 -> 不重试
    # 单图编辑 (relational 无轴测参考): 只送空房照一张
    assert len(relay.calls) == 1 and len(relay.calls[0]["images"]) == 1
    assert "家具布置约束" in relay.calls[0]["prompt"]


def test_relational_missing_room_id_400(client_fal):
    """relational 需要 room_id (编译简报); 缺则 400 且预扣回退、provider 未被调。"""
    c, relay, _fal, _set = client_fal
    from test_render_real_geometry import _PNG

    r = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": "", "direction": ""},
    )
    assert r.status_code == 201, r.text
    photo = r.json()
    resp = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert resp.status_code == 400
    assert resp.json()["code"] == "RELATIONAL_NOT_READY"
    assert len(relay.calls) == 0
    assert main._budget.status()["daily_count"] == 0


def test_relational_rejects_bad_strategy_and_misplaced_backend(client_fal):
    c, relay, _fal, _set = client_fal
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "magic"},
    )
    assert r.status_code == 400
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "relational", "backend": "fal"},
    )
    assert r.status_code == 400 and "geometry_lock" in r.json()["error"]
    assert len(relay.calls) == 0


def test_geometry_lock_requires_calibration(client_fal):
    """geometry_lock 备用档: 未标定照片 400 (不再静默落软参考)。"""
    c, relay, _fal, _set = client_fal
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "geometry_lock"},
    )
    assert r.status_code == 400 and "标定" in r.json()["error"]
    assert len(relay.calls) == 0


def test_relational_retries_once_on_fail_and_records_rounds(client_fal):
    """F003 闭环: round1 有 fail -> 修正 prompt 重试 1 次; round2 达标 -> 交付, rounds=2。"""
    c, relay, _fal, _set = client_fal
    relay.chat_responses = [_FAIL_ONE, _PASS_ALL]
    photo = _upload(c)
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["rounds"] == 2
    assert len(relay.calls) == 2
    # 修正 prompt 回写了 fail 约束 (上轮问题逐条改正)
    assert "上一次生成结果存在以下问题" in relay.calls[1]["prompt"]
    # 两次独立预扣 (round1 + round2)
    assert main._budget.status()["daily_count"] == 2


def test_relational_picks_better_round_not_latest(client_fal):
    """F003: 两轮都失败时取验收分高者 (评测实证 round2 可能回归 —— 允许 round1 回退)。"""
    c, relay, _fal, _set = client_fal
    # round1: 1 fail; round2: 2 fail (更差) -> 交付 round1
    relay.chat_responses = [_FAIL_ONE, _FAIL_WORSE]
    photo = _upload(c)
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["rounds"] == 2
    assert rec["relation_check"]["nfail"] == 1  # 交付的是 round1 (较好), 不是 round2


def test_relational_vlm_degraded_skips_retry_and_marks(client_fal):
    """VLM 异常 -> 降级直交付不重试 (VLM 挂了重出图没用), 记录 degraded。"""
    c, relay, _fal, _set = client_fal

    def boom(messages, **kw):
        raise RuntimeError("vlm down")

    relay.chat_json = boom
    photo = _upload(c)
    r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert rec["rounds"] == 1
    assert rec["relation_check"]["degraded"] is True
    assert main._budget.status()["daily_count"] == 1


def test_softref_strategy_preserves_legacy_path(client_fal):
    """softref 快速预览档: 走原轴测软参考 (多图 edits, 记录无 relation_check)。"""
    c, relay, _fal, _set = client_fal
    photo = _upload(c)
    r = c.post(
        "/api/projects/D/schemes/default/render-real",
        json={"photo_id": photo["id"], "strategy": "softref"},
    )
    assert r.status_code == 200, r.text
    job = _wait(c, r.json()["job_id"])
    rec = job["result"]
    assert "relation_check" not in rec
    assert len(relay.calls[0]["images"]) >= 2  # 空房照 + 轴测参考


def test_placement_brief_preview_endpoint(client_fal):
    """F004: 简报预览端点 —— 只读、与 relational 出图同一份约束, 缺 room_id 400。"""
    c, relay, _fal, _set = client_fal
    photo = _upload(c)
    r = c.get(f"/api/projects/D/schemes/default/placement-brief?photo_id={photo['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["brief"]["constraints"]
    assert body["brief"]["frame"]  # direction=v1 -> 有画面四至
    assert len(relay.calls) == 0  # 纯计算, 不调 provider

    from test_render_real_geometry import _PNG

    r2 = c.post(
        "/api/projects/D/baselines/v1/photos",
        files={"file": ("room.png", _PNG, "image/png")},
        data={"room_id": "", "direction": ""},
    )
    photo2 = r2.json()
    r3 = c.get(f"/api/projects/D/schemes/default/placement-brief?photo_id={photo2['id']}")
    assert r3.status_code == 400
    assert r3.json()["code"] == "RELATIONAL_NOT_READY"


def test_relational_round2_budget_exhausted_delivers_round1(client_fal):
    """F005 NB-1: round2 预扣撞预算上限 -> 静默交付 round1, 不丢已付费成果、不报 402。"""
    from aigc.errors import BudgetExceeded

    c, relay, _fal, _set = client_fal
    relay.chat_responses = [_FAIL_ONE, _PASS_ALL]
    photo = _upload(c)
    orig_reserve = main._budget.reserve
    calls = {"n": 0}

    def flaky_reserve(house):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise BudgetExceeded("daily cap")
        return orig_reserve(house)

    main._budget.reserve = flaky_reserve
    try:
        r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
        assert r.status_code == 200, r.text
        job = _wait(c, r.json()["job_id"])
        assert job["status"] == "done", job  # 未 402/未 error: round1 照常交付
        rec = job["result"]
        assert rec["rounds"] == 1  # round2 未发生 (预扣被拒即收)
        assert len(relay.calls) == 1
    finally:
        main._budget.reserve = orig_reserve
