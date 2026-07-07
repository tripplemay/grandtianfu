# -*- coding: utf-8 -*-
"""DELETE /schemes/{scheme_id}/renders/{render_id}: 摘记录 + unlink 自有 4 文件,
保留共享 photo_url; default 双账本(方案级+legacy)同摘; 404/幂等。产物全指向 tmp。"""
import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main
from aigc.artifacts import ArtifactStore
from aigc.config import Settings
from aigc.records import RenderLog


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), (200, 190, 170)).save(buf, format="PNG")
    return buf.getvalue()


def _settings(tmp_path) -> Settings:
    return Settings(
        provider="openai", base_url="https://relay/v1", api_key="sk-test", model="gpt-image-2",
        proxy=None, request_timeout_s=300.0,
        artifacts_dir=str(tmp_path / "art"), uploads_dir=str(tmp_path / "up"),
        max_images_per_project=5, daily_image_cap=10,
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
    monkeypatch.setattr(main, "DATA_DIR", str(data_root))
    monkeypatch.setattr(main, "GEOM_READONLY", False)
    monkeypatch.setattr(main, "_settings", s)
    monkeypatch.setattr(main, "_artifacts", ArtifactStore(s.artifacts_dir))
    monkeypatch.setattr(main, "_uploads", ArtifactStore(s.uploads_dir))
    monkeypatch.setattr(main, "_renders", RenderLog(s.artifacts_dir))
    return TestClient(main.app), data_root, s


def _make_render(art: ArtifactStore, scope: str, *, with_shared_photo=True) -> dict:
    """在 ARTIFACTS 落 4 自有文件 (+ 1 共享 photo), 返回一条 real-photo 记录。"""
    out = art.save_scoped(_png(), project_id="D", scope_id=scope, kind="real-render")
    base = art.save_scoped(_png(), project_id="D", scope_id=scope, kind="real-base")
    thumb = art.save_scoped(_png(), project_id="D", scope_id=scope, kind="real-thumb", ext="webp")
    prev = art.save_scoped(_png(), project_id="D", scope_id=scope, kind="real-preview", ext="webp")
    rid = out.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    rec = {
        "id": rid, "mode": "real-photo", "scheme_id": scope, "model": "gpt-image-2",
        "url": f"/api/artifacts/{out}", "base_url": f"/api/artifacts/{base}",
        "thumb_url": f"/api/artifacts/{thumb}", "preview_url": f"/api/artifacts/{prev}",
    }
    if with_shared_photo:
        photo = art.save_scoped(_png(), project_id="D", scope_id="empty", kind="empty")
        rec["photo_url"] = f"/api/artifacts/{photo}"
    return rec


def _seed_scheme_renders(data_root: Path, scheme_id: str, records: list) -> None:
    d = data_root / "D" / "schemes" / scheme_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "renders.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def _abs(art: ArtifactStore, url: str) -> Path:
    # 直接拼真实路径 (不经 resolve 的 is_file 门), 便于删后断言 .exists() 为假。
    return Path(art.root) / url[len("/api/artifacts/"):]


def test_delete_render_removes_record_and_own_files_keeps_shared_photo(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    rec = _make_render(art, "default")
    _seed_scheme_renders(data_root, "default", [rec])
    own = [_abs(art, rec[k]) for k in ("url", "base_url", "thumb_url", "preview_url")]
    photo = _abs(art, rec["photo_url"])
    assert all(p.is_file() for p in own) and photo.is_file()

    r = c.delete(f"/api/projects/D/schemes/default/renders/{rec['id']}")

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deleted": rec["id"], "files_removed": 4}
    # 记录摘除
    left = json.loads((data_root / "D" / "schemes" / "default" / "renders.json").read_text("utf-8"))
    assert left == []
    # 4 自有文件删除, 共享 photo 保留
    assert all(not p.exists() for p in own)
    assert photo.is_file()


def test_delete_render_404_on_unknown_id(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    _seed_scheme_renders(data_root, "default", [_make_render(art, "default")])
    r = c.delete("/api/projects/D/schemes/default/renders/nope")
    assert r.status_code == 404, r.text


def test_delete_render_idempotent_when_files_already_gone(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    rec = _make_render(art, "default")
    _seed_scheme_renders(data_root, "default", [rec])
    _abs(art, rec["url"]).unlink()  # 文件先被 gc 删掉一枚
    r = c.delete(f"/api/projects/D/schemes/default/renders/{rec['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["files_removed"] == 3  # 剩余 3 个仍删, 缺失的跳过


def test_delete_render_latest_recomputed(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    newest = _make_render(art, "default")
    older = _make_render(art, "default")
    _seed_scheme_renders(data_root, "default", [newest, older])  # 最新在前
    c.delete(f"/api/projects/D/schemes/default/renders/{newest['id']}")
    left = c.get("/api/projects/D/schemes/default/renders").json()
    assert [x["id"] for x in left] == [older["id"]]  # latest 回落到 older


def test_delete_render_default_also_removes_legacy_account(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    rec = _make_render(art, "default")
    # 只存在于 legacy 账本 (方案级为空); 删除须命中 legacy, 否则经合并复活。
    main._renders.append("D", rec)
    _seed_scheme_renders(data_root, "default", [])
    r = c.delete(f"/api/projects/D/schemes/default/renders/{rec['id']}")
    assert r.status_code == 200, r.text
    assert main._renders.list("D") == []
    assert not _abs(art, rec["url"]).exists()


def test_delete_render_non_default_scheme(client):
    c, data_root, s = client
    art = ArtifactStore(s.artifacts_dir)
    rec = _make_render(art, "scheme_x")
    _seed_scheme_renders(data_root, "scheme_x", [rec])
    # 非 default 方案需 meta 才通过 _require_scheme
    (data_root / "D" / "schemes" / "scheme_x" / "meta.json").write_text(
        json.dumps({"id": "scheme_x", "name": "X", "source": "manual", "baseline_version_id": "v1"}),
        encoding="utf-8",
    )
    r = c.delete(f"/api/projects/D/schemes/scheme_x/renders/{rec['id']}")
    assert r.status_code == 200, r.text
    assert not _abs(art, rec["url"]).exists()
