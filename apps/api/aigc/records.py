# -*- coding: utf-8 -*-
"""AI 渲染历史: {root}/{project}/renders.json (列表, 最新在前)。

与产物 PNG 同根 (ARTIFACTS_DIR; 生产 bind 挂载 + 备份)。它是 .json, 不经 /api/artifacts 服务
(resolve 白名单仅位图), 由 GET /renders 专用端点返回。多 job 线程并发 append 用 _LOCK 串行化。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()


class RenderLog:
    def __init__(self, root: str):
        self._root = Path(root)

    def _path(self, project_id: str) -> Path:
        return self._root / project_id / "renders.json"

    def _load(self, project_id: str) -> list:
        try:
            data = json.loads(self._path(project_id).read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def append(self, project_id: str, record: dict, *, cap: int = 200) -> None:
        """新记录插到队首并落盘 (原子); cap 上限淘汰最旧, 防无限增长。"""
        with _LOCK:
            items = self._load(project_id)
            items.insert(0, record)
            del items[cap:]
            path = self._path(project_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)

    def list(self, project_id: str) -> list:
        return self._load(project_id)

    def set_status(
        self,
        project_id: str,
        render_id: str,
        status: str,
        *,
        feedback_reason: str | None = None,
    ) -> dict | None:
        """给 legacy 账本里一条记录写验收/确认状态 (工作流改造 F/B4)。

        default 方案历史经 _list_default_renders 合并 legacy 账本, 故对 default 的老出图记录
        改 status 须回退到此账本 (方案级 renders.json 查不到会 404)。与 delete 的双账本回退对称。
        不校验 status 词表 (调用方 set_render_status 已先校验); 未命中返回 None。持 _LOCK 串行。
        """
        with _LOCK:
            items = self._load(project_id)
            updated: dict | None = None
            for idx, rec in enumerate(items):
                if (
                    isinstance(rec, dict)
                    and (rec.get("id") == render_id or rec.get("url") == render_id)
                ):
                    new_rec = dict(rec)
                    new_rec["status"] = status
                    if feedback_reason is not None:
                        new_rec["feedback_reason"] = feedback_reason.strip() or None
                    items[idx] = new_rec
                    updated = new_rec
                    break
            if updated is not None:
                path = self._path(project_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)
            return updated

    def set_comment(
        self,
        project_id: str,
        render_id: str,
        comment: str | None,
    ) -> dict | None:
        """给 legacy 账本里一条记录写单条可编辑备注 (render-note-b1)。

        与 set_status 对称: default 方案历史经 _list_default_renders 合并 legacy 账本, 故对
        default 老出图写备注须回退到此账本 (方案级 renders.json 查不到会 404)。comment 归一化同
        set_render_status 对 feedback_reason 的处理 (str -> strip or None; 其余 -> None); 词表/
        长度校验由调用方 normalize_render_comment 先行。未命中返回 None。持 _LOCK 串行。
        """
        normalized = (comment.strip() or None) if isinstance(comment, str) else None
        with _LOCK:
            items = self._load(project_id)
            updated: dict | None = None
            for idx, rec in enumerate(items):
                if (
                    isinstance(rec, dict)
                    and (rec.get("id") == render_id or rec.get("url") == render_id)
                ):
                    new_rec = dict(rec)
                    new_rec["comment"] = normalized
                    items[idx] = new_rec
                    updated = new_rec
                    break
            if updated is not None:
                path = self._path(project_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)
            return updated

    def remove(self, project_id: str, render_id: str) -> dict | None:
        """摘除一条 legacy 记录 (按 id, 缺 id 回退 url), 返回被删记录; 未命中返回 None。

        default 方案的效果图历史经 _list_default_renders 合并 legacy 账本; 删除须双账本
        同摘, 否则被删记录会经合并复活。持 _LOCK 与 append 串行。
        """
        with _LOCK:
            items = self._load(project_id)
            removed: dict | None = None
            kept: list = []
            for rec in items:
                if (
                    removed is None
                    and isinstance(rec, dict)
                    and (rec.get("id") == render_id or rec.get("url") == render_id)
                ):
                    removed = rec
                    continue
                kept.append(rec)
            if removed is not None:
                path = self._path(project_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)
            return removed
