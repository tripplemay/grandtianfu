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
