# -*- coding: utf-8 -*-
"""生成产物 / 上传图 的落盘与防穿越服务。

产物自托管: provider 返回的图解码落盘 ARTIFACTS_DIR, 经 /api/artifacts 同源服务 ——
免 CSP 放行外域、保证持久与可备份 (生产 bind 挂载 + 异地备份)。
安全: 段名白名单 + 解析后必须落在根目录内 (拒 ../、绝对路径、符号链接逃逸)。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

# 服务/落盘仅限位图扩展名: 故意排除 svg —— 同源内联 image/svg+xml 可执行 <script> (存储型 XSS);
# 轴测 SVG 是内部中间物, 不进可服务产物目录 (第5步先栅格成 PNG)。
_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
_SAFE_EXT = {"png", "jpg", "jpeg", "webp"}


def _safe_seg(s: str) -> bool:
    return bool(s) and all(c in _SAFE for c in s)


class ArtifactStore:
    """ARTIFACTS_DIR 根下按 {project_id}/{kind}/{uuid}.{ext} 落盘, 防路径穿越。"""

    def __init__(self, root: str):
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def save(self, data: bytes, *, project_id: str, kind: str, ext: str = "png") -> str:
        if not _safe_seg(project_id) or not _safe_seg(kind):
            raise ValueError("project_id/kind 非法 (仅 [A-Za-z0-9_-])")
        if ext.lower() not in _SAFE_EXT:
            raise ValueError(f"扩展名不允许: {ext!r}")
        rel = f"{project_id}/{kind}/{uuid.uuid4().hex}.{ext.lower()}"
        dest = self._root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        with open(tmp, "wb") as fh:  # fsync: 掉电不留半截 PNG (renders.json 已有记录时=永久碎图)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
        return rel

    def save_scoped(
        self,
        data: bytes,
        *,
        project_id: str,
        scope_id: str,
        kind: str,
        ext: str = "png",
    ) -> str:
        if not _safe_seg(project_id) or not _safe_seg(scope_id) or not _safe_seg(kind):
            raise ValueError("project_id/scope_id/kind 非法 (仅 [A-Za-z0-9_-])")
        if ext.lower() not in _SAFE_EXT:
            raise ValueError(f"扩展名不允许: {ext!r}")
        rel = f"{project_id}/{scope_id}/{kind}/{uuid.uuid4().hex}.{ext.lower()}"
        dest = self._root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
        return rel

    def resolve(self, rel_path: str) -> Path | None:
        """把相对路径解析为根内真实文件; 越界 / 非白名单扩展名 / 点开头 / 非文件 -> None。

        扩展名白名单 + 拒点开头文件: 杜绝 _budget.json / *.bak / .tmp 等非图像内部文件
        被 GET /api/artifacts 取回 (簿记/状态信息泄露)。
        """
        target = (self._root / rel_path).resolve()
        try:
            rel = target.relative_to(self._root)
        except ValueError:
            return None  # 穿越尝试 (resolve 已展开 .. 与符号链接)
        if target.suffix.lstrip(".").lower() not in _SAFE_EXT:
            return None
        if any(part.startswith(".") for part in rel.parts):
            return None
        return target if target.is_file() else None
