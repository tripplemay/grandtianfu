# -*- coding: utf-8 -*-
"""墙面材质C (P2) API: photos.purpose 校验 + 墙面参考图解析 (确定性序/去重/上限/按房) +
provider ≤4 参考图闸门。"""
import pytest

import baselines
import main
from aigc.artifacts import ArtifactStore
from aigc.config import Settings
from aigc.errors import ProviderError
from aigc.providers import MAX_EDIT_IMAGES, OpenAIImageProvider


def test_photo_purpose_validation():
    baselines._validate_photo_fields({"purpose": "wall_material"})  # ok
    baselines._validate_photo_fields({"purpose": "empty"})  # ok
    baselines._validate_photo_fields({"purpose": None})  # ok (缺省=空房底图)
    with pytest.raises(baselines.BaselineValidationError):
        baselines._validate_photo_fields({"purpose": "bogus"})


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    up = ArtifactStore(str(tmp_path / "up"))
    monkeypatch.setattr(main, "_uploads", up)
    return up


def _seed_photos(up: ArtifactStore, n: int) -> list[dict]:
    out = []
    for i in range(n):
        rel = up.save(b"\x89PNG\r\n\x1a\n" + bytes([i]), project_id="D", kind="wall", ext="png")
        out.append({"id": f"p{i}", "url": f"/api/uploads/{rel}"})
    return out


def test_resolve_wall_photos_order_dedup_cap_and_room_filter(uploads):
    photos = _seed_photos(uploads, 3)
    G = {
        "rooms": [
            {"id": "r1", "walls": {"S": {"photo_id": "p1"}, "N": {"photo_id": "p0"}}},
            {"id": "r2", "walls": {"E": {"photo_id": "p2"}, "W": {"photo_id": "p0"}}},
        ]
    }
    # 全宅: 房序 r1,r2 + 边序 N,S,E,W; p0 在 r2.W 重复 -> 去重。
    out = main._resolve_wall_material_photos(G, photos, None, cap=4)
    assert [pid for pid, _ in out] == ["p0", "p1", "p2"]
    # 上限。
    assert [pid for pid, _ in main._resolve_wall_material_photos(G, photos, None, cap=1)] == ["p0"]
    # 按房过滤 r2: 边序 E(p2) 先于 W(p0)。
    assert [pid for pid, _ in main._resolve_wall_material_photos(G, photos, "r2", cap=4)] == ["p2", "p0"]
    # cap<=0 或无 walls -> 空。
    assert main._resolve_wall_material_photos(G, photos, None, cap=0) == []
    assert main._resolve_wall_material_photos({"rooms": [{"id": "x"}]}, photos, None, cap=4) == []


def test_resolve_wall_photos_skips_missing_and_returns_bytes(uploads):
    photos = _seed_photos(uploads, 1)  # only p0 exists
    G = {"rooms": [{"id": "r1", "walls": {"N": {"photo_id": "p0"}, "S": {"photo_id": "ghost"}}}]}
    out = main._resolve_wall_material_photos(G, photos, None, cap=4)
    assert [pid for pid, _ in out] == ["p0"]  # 缺失的 ghost 静默跳过
    assert out[0][1].startswith(b"\x89PNG")


def _settings() -> Settings:
    return Settings(
        provider="openai", base_url="http://x", api_key="k", model="gpt-image-2", proxy=None,
        request_timeout_s=1.0, artifacts_dir="/tmp", uploads_dir="/tmp",
        max_images_per_project=1, daily_image_cap=1,
    )


def test_provider_edit_rejects_over_cap():
    prov = OpenAIImageProvider(_settings())
    with pytest.raises(ProviderError):
        prov.edit("p", [b"a"] * (MAX_EDIT_IMAGES + 1), size="1024x1024")
