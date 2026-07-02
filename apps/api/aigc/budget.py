# -*- coding: utf-8 -*-
"""预算护栏: 文件落盘的原子计数 (预扣 reserve / 释放 release), 跨重启保留。

为何预扣: 生成式无确定性且计费, 架构红线"AI 预算原子预扣 + provider 硬额度"。
两个并发任务必须先各自 reserve 过闸, 防同时通过检查再双双烧钱。
并发模型: Dockerfile 固定单 uvicorn worker -> 进程内 threading.Lock 串行化 read-modify-write 即足够。
caps: 每项目累计张数 + 全局当日张数 (跨天自动归零)。token 仅计量不设闸 ($/token 未知)。
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .config import Settings
from .errors import BudgetExceeded

_LOCK = threading.Lock()


def _today() -> str:
    return time.strftime("%Y-%m-%d")


class BudgetGuard:
    def __init__(self, settings: Settings, path: str | None = None):
        self._s = settings
        self._path = Path(path or os.path.join(settings.artifacts_dir, "_budget.json"))

    def _load(self) -> dict:
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError
            d.setdefault("day", _today())
            d.setdefault("daily_count", 0)
            d.setdefault("per_project", {})
            d.setdefault("total_tokens", 0)
            d.setdefault("furnish_daily_count", 0)
            return d
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return {
                "day": _today(),
                "daily_count": 0,
                "per_project": {},
                "total_tokens": 0,
                "furnish_daily_count": 0,
            }

    def _save(self, d: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    def reserve(self, project_id: str) -> None:
        """生成前预扣一张; 超限抛 BudgetExceeded (路由层映射 402)。失败须 release()。"""
        with _LOCK:
            d = self._load()
            if d["day"] != _today():  # 跨天: 当日计数归零 (项目累计不归零)
                d["day"] = _today()
                d["daily_count"] = 0
            used = int(d["per_project"].get(project_id, 0))
            if used >= self._s.max_images_per_project:
                raise BudgetExceeded(
                    f"项目 {project_id} 已达生成上限 {self._s.max_images_per_project} 张"
                )
            if int(d["daily_count"]) >= self._s.daily_image_cap:
                raise BudgetExceeded(f"今日生成已达上限 {self._s.daily_image_cap} 张")
            d["daily_count"] = int(d["daily_count"]) + 1
            d["per_project"][project_id] = used + 1
            self._save(d)

    def release(self, project_id: str) -> None:
        """回退一次预扣 —— 仅当对应 reserve 成功且其后生成失败时调用一次 (契约: 每次预扣至多一次释放)。

        跨天保护: 若已进入新一天, 旧日的 daily_count 已无意义, 不再对新日计数 -1
        (否则把今天的额度越扣); 仅回退 per_project 累计。max(0) 兜底防越扣为负。
        """
        with _LOCK:
            d = self._load()
            if d["day"] == _today():
                d["daily_count"] = max(0, int(d["daily_count"]) - 1)
            else:
                d["day"] = _today()
                d["daily_count"] = 0
            d["per_project"][project_id] = max(0, int(d["per_project"].get(project_id, 0)) - 1)
            self._save(d)

    def reserve_furnish(self) -> None:
        """AI 摆家具计次闸 (每日全局): 超限抛 BudgetExceeded (402)。

        计次不回退 (chat 尝试即计, 防失败重试刷量); 跨天自动归零。
        """
        with _LOCK:
            d = self._load()
            if d["day"] != _today():
                d["day"] = _today()
                d["daily_count"] = 0
                d["furnish_daily_count"] = 0
            used = int(d.get("furnish_daily_count", 0))
            if used >= self._s.furnish_daily_cap:
                raise BudgetExceeded(f"今日 AI 摆家具已达上限 {self._s.furnish_daily_cap} 次")
            d["furnish_daily_count"] = used + 1
            self._save(d)

    def record_tokens(self, usage: dict) -> None:
        """累计 provider usage token (仅计量, 供监控/成本估算)。"""
        with _LOCK:
            d = self._load()
            d["total_tokens"] = int(d.get("total_tokens", 0)) + int((usage or {}).get("total_tokens", 0) or 0)
            self._save(d)

    def status(self) -> dict:
        d = self._load()
        return {
            "day": d["day"],
            "daily_count": int(d["daily_count"]),
            "daily_cap": self._s.daily_image_cap,
            "per_project_cap": self._s.max_images_per_project,
            "total_tokens": int(d.get("total_tokens", 0)),
            "furnish_daily_count": int(d.get("furnish_daily_count", 0)),
            "furnish_daily_cap": self._s.furnish_daily_cap,
        }
