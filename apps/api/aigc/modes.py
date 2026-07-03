# -*- coding: utf-8 -*-
"""渲染产物 mode 注册表 (审计 P1-2)。

renders.json 的 mode 此前是自由字符串 + 前端负向过滤 (!=='real-photo') —— 新增第三种
mode 会静默混进轴测效果图列表。此处为唯一词表: 写入前校验, artifact kind 从表取值。
"""
from __future__ import annotations

AXON_PHOTOREAL = "axon-photoreal"  # 第5步: 轴测底图 -> 照片级轴测效果图
REAL_PHOTO = "real-photo"          # 第7步: 空房照+轴测参考 -> 实拍效果图

RENDER_MODES: dict[str, dict] = {
    AXON_PHOTOREAL: {"artifact_kind": "ai-render", "base_kind": "ai-base"},
    REAL_PHOTO: {"artifact_kind": "real-render", "base_kind": "real-base"},
}
