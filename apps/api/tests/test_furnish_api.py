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
