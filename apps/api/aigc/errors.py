# -*- coding: utf-8 -*-
"""AI 子系统类型化异常 (供路由层映射到对应 HTTP 状态码)。"""
from __future__ import annotations


class AIError(Exception):
    """AI 子系统基类异常 -> 500 (除非更具体子类)。"""


class ProviderError(AIError):
    """图像 provider 调用失败 (网络/非200/无图) -> 502。"""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


class BudgetExceeded(AIError):
    """预算/配额超限 -> 402。"""


class DependencyUnavailable(AIError):
    """运行时系统依赖缺失 (如 rsvg-convert / librsvg2-bin) -> 503。

    区别于 AIError(500, 逻辑错误) 与 ProviderError(502, 上游服务)：503 语义 =
    服务本身缺必需的本地依赖 (环境/部署问题, 可诊断可修复), 非代码崩溃。
    """
