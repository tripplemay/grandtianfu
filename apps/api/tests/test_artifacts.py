# -*- coding: utf-8 -*-
"""产物存储: 落盘路径形态、字节回读、扩展名白名单、路径穿越防护。"""
import pytest

from aigc.artifacts import ArtifactStore


def test_save_returns_scoped_path_and_writes_bytes(tmp_path):
    s = ArtifactStore(str(tmp_path))
    rel = s.save(b"PNGDATA", project_id="D", kind="render", ext="png")
    assert rel.startswith("D/render/") and rel.endswith(".png")
    assert (tmp_path / rel).read_bytes() == b"PNGDATA"


def test_save_scoped_returns_project_scheme_kind_path(tmp_path):
    s = ArtifactStore(str(tmp_path))
    rel = s.save_scoped(
        b"PNGDATA",
        project_id="D",
        scope_id="scheme_ai_001",
        kind="ai-render",
        ext="png",
    )
    assert rel.startswith("D/scheme_ai_001/ai-render/") and rel.endswith(".png")
    assert (tmp_path / rel).read_bytes() == b"PNGDATA"
    assert s.resolve(rel) is not None


def test_resolve_valid_and_traversal(tmp_path):
    s = ArtifactStore(str(tmp_path))
    rel = s.save(b"x", project_id="D", kind="render")
    assert s.resolve(rel) is not None
    # 路径穿越尝试 -> None
    assert s.resolve("../../../../etc/passwd") is None
    assert s.resolve("D/render/../../../etc/passwd") is None


def test_resolve_missing_is_none(tmp_path):
    s = ArtifactStore(str(tmp_path))
    assert s.resolve("D/render/nonexistent.png") is None


def test_save_rejects_unsafe_segments(tmp_path):
    s = ArtifactStore(str(tmp_path))
    with pytest.raises(ValueError):
        s.save(b"x", project_id="../evil", kind="render")
    with pytest.raises(ValueError):
        s.save(b"x", project_id="D", kind="r/../e")
    with pytest.raises(ValueError):
        s.save(b"x", project_id="D", kind="render", ext="exe")
    with pytest.raises(ValueError):
        s.save_scoped(b"x", project_id="D", scope_id="../evil", kind="render")
