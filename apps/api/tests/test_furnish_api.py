# -*- coding: utf-8 -*-
"""POST /furnish: async AI furniture generation writes candidate schemes."""
import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

import main
from aigc.budget import BudgetGuard
from aigc.config import Settings


def _settings(tmp_path, **over):
    base = dict(
        provider="openai",
        base_url="https://relay/v1",
        api_key="sk-test",
        model="gpt-5.5",
        proxy=None,
        request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"),
        uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5,
        daily_image_cap=10,
    )
    base.update(over)
    return Settings(**base)


class FakeProvider:
    def chat_json(self, messages, *, model=None, temperature=0.2):
        # Phase C-2 契约: AI 出 name + 富化 style_prompt (+ 可选同组 swaps); 不落位。
        return {
            "schemes": [
                {"name": "轻奢 A", "style_prompt": "现代轻奢, 米白大理石+黄铜点缀"},
                {"name": "自然 B", "style_prompt": "原木自然, 燕麦色棉麻"},
            ]
        }


def _client(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    data_root = tmp_path / "projects"
    project = data_root / "D"
    project.mkdir(parents=True)
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "geometry.json", project / "geometry.json")
    shutil.copyfile(repo_root / "data" / "projects" / "D" / "furniture.json", project / "furniture.json")
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "_settings", _settings(tmp_path))
    monkeypatch.setattr(
        main, "_budget", BudgetGuard(_settings(tmp_path), path=str(tmp_path / "_budget.json"))
    )
    monkeypatch.setattr(main, "get_provider", lambda _s: FakeProvider())
    return TestClient(main.app), project


def _wait(client, job_id, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/ai/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job timeout")


def test_furnish_503_when_ai_disabled(tmp_path, monkeypatch):
    client, _project = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "_settings", _settings(tmp_path, api_key="", base_url=""))

    r = client.post("/api/projects/D/furnish", json={"style_prompt": "现代", "count": 2})

    assert r.status_code == 503


def test_furnish_validates_count(tmp_path, monkeypatch):
    client, _project = _client(tmp_path, monkeypatch)

    r = client.post("/api/projects/D/furnish", json={"style_prompt": "现代", "count": 0})

    assert r.status_code == 400


def test_furnish_404_for_unknown_base_scheme(tmp_path, monkeypatch):
    client, _project = _client(tmp_path, monkeypatch)

    r = client.post(
        "/api/projects/D/furnish",
        json={"style_prompt": "现代", "count": 1, "base_scheme_id": "missing"},
    )

    assert r.status_code == 404


def test_furnish_job_creates_ai_schemes_without_overwriting_root(tmp_path, monkeypatch):
    client, project = _client(tmp_path, monkeypatch)
    root_before = json.loads((project / "furniture.json").read_text(encoding="utf-8"))

    r = client.post(
        "/api/projects/D/furnish",
        json={"style_prompt": "现代轻奢", "count": 2, "base_scheme_id": "default"},
    )
    assert r.status_code == 200, r.text
    job = _wait(client, r.json()["job_id"])

    assert job["status"] == "done", job
    result = job["result"]
    assert len(result["schemes"]) == 2
    # 审计 P2-6: 生成溯源落 meta (model / furnish_warnings / catalog_rev)。
    first_meta = client.get(f"/api/projects/D/schemes/{result['schemes'][0]['id']}").json()
    assert first_meta["model"]
    assert isinstance(first_meta.get("furnish_warnings"), list)
    assert first_meta["catalog_rev"] >= 1
    assert result["schemes"][0]["id"].startswith("scheme_ai_")
    schemes = client.get("/api/projects/D/schemes").json()
    ai_schemes = [s for s in schemes if s["source"] == "ai"]
    assert len(ai_schemes) == 2
    first_id = result["schemes"][0]["id"]
    meta = client.get(f"/api/projects/D/schemes/{first_id}").json()
    assert meta["source"] == "ai"
    assert meta["base_scheme_id"] == "default"
    # Phase C-2: 候选 = 基线锁定布局 (件数与 base 一致, 不落位/不增删) + AI 富化 style_prompt。
    furniture = client.get(f"/api/projects/D/schemes/{first_id}/furniture").json()
    assert len(furniture) == len(root_before)  # 布局件数不变
    assert meta["style_prompt"] == "现代轻奢, 米白大理石+黄铜点缀"  # 用 AI 富化 prompt
    assert json.loads((project / "furniture.json").read_text(encoding="utf-8")) == root_before


def test_furnish_snapshot_recorded_on_scheme_meta(tmp_path, monkeypatch):
    """P0-2: 新 AI 方案 meta 落 furnish_snapshot (提交时 baseline/几何/家具哈希) 供审计溯源。"""
    client, _project = _client(tmp_path, monkeypatch)
    r = client.post(
        "/api/projects/D/furnish", json={"style_prompt": "现代轻奢", "count": 1}
    )
    assert r.status_code == 200, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    meta = client.get(f"/api/projects/D/schemes/{job['result']['schemes'][0]['id']}").json()
    snap = meta["furnish_snapshot"]
    assert snap["baseline_version_id"] == "v1"
    assert meta["baseline_version_id"] == "v1"
    # 快照哈希须等于实际基准几何/家具的哈希 (非任意真值, 防错对象被哈希)。
    G = json.loads((_project / "geometry.json").read_text(encoding="utf-8"))
    base_furniture = json.loads((_project / "furniture.json").read_text(encoding="utf-8"))
    assert snap["geometry_hash"] == main._stable_hash(G.get("rooms", []))
    assert snap["furniture_hash"] == main._stable_hash(base_furniture)


def test_furnish_fails_when_baseline_drifts_during_job(tmp_path, monkeypatch):
    """P0-2 核心: 提交->执行窗口内 confirm 新 baseline -> job 报错 (候选不静默误绑新版本)。

    手法 B (确定性, 无线程): monkeypatch submit 捕获闭包不执行 -> 中途 confirm v2 -> 手动跑闭包。
    """
    client, _project = _client(tmp_path, monkeypatch)
    captured = {}
    monkeypatch.setattr(
        main._jobs, "submit", lambda fn, *, meta=None: (captured.update(fn=fn), "job_x")[1]
    )
    # 提交 furnish (快照 snap_baseline_id=v1, 闭包被捕获未执行)。
    r = client.post("/api/projects/D/furnish", json={"style_prompt": "现代轻奢", "count": 1})
    assert r.status_code == 200, r.text
    assert "fn" in captured
    # 窗口内 confirm 新 baseline v2 (current 漂移 v1->v2)。
    assert client.post("/api/projects/D/baselines", json={"source_version_id": "v1"}).status_code == 201
    assert client.post("/api/projects/D/baselines/v2/confirm").status_code == 200
    # 手动执行闭包 -> 应因 baseline 漂移报错, 不静默把候选绑到 v2。
    import pytest

    with pytest.raises(ValueError, match="户型版本已更新"):
        captured["fn"]()
    # 未产生任何 v2 的 AI 方案 (未静默误绑)。
    schemes = client.get("/api/projects/D/schemes").json()
    assert not [s for s in schemes if s.get("source") == "ai"]
    # 不变量 d: 提交时已扣的每日次数不因 job 失败而退还 (防失败重试刷量; 已知取舍)。
    budget = client.get("/api/ai/status").json()["budget"]
    assert budget["furnish_daily_count"] == 1


def test_furnish_402_when_daily_cap_exhausted(tmp_path, monkeypatch):
    client, _project = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        main,
        "_budget",
        BudgetGuard(
            _settings(tmp_path, furnish_daily_cap=1),
            path=str(tmp_path / "_budget_cap.json"),
        ),
    )

    first = client.post(
        "/api/projects/D/furnish", json={"style_prompt": "现代轻奢", "count": 1}
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/projects/D/furnish", json={"style_prompt": "现代轻奢", "count": 1}
    )
    assert second.status_code == 402
    assert "上限" in second.json()["error"]
