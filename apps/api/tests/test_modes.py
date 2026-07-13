# -*- coding: utf-8 -*-
"""渲染 mode 注册表 (modes.py): kind 词表单一真源, 含 thumb_kind (F002)。"""
from aigc.modes import AXON_PHOTOREAL, REAL_PHOTO, RENDER_MODES


def test_render_modes_have_all_kind_fields():
    # 每个渲染 mode 必须齐备 artifact/base/thumb 三类 kind, 供 main.py 从注册表取值 (消除硬编码)。
    for mode in (AXON_PHOTOREAL, REAL_PHOTO):
        entry = RENDER_MODES[mode]
        for field in ("artifact_kind", "base_kind", "thumb_kind"):
            assert field in entry and entry[field], f"{mode} 缺 {field}"


def test_render_modes_thumb_kind_values():
    # F002: 缩略图 kind 收入注册表, 值与历史写盘字面一致 (不改既有 artifact kind 语义)。
    assert RENDER_MODES[AXON_PHOTOREAL]["thumb_kind"] == "ai-thumb"
    assert RENDER_MODES[REAL_PHOTO]["thumb_kind"] == "real-thumb"
