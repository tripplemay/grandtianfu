# -*- coding: utf-8 -*-
"""AI 子系统配置: 全部来自环境变量, 启动期一次性读取。

设计要点:
  - **AI 凭据缺失不让整服务崩** (现有 geometry/render 端点必须照常)。无 OPENAI_API_KEY 时
    ai_enabled=False, AI 端点返回 503, 其余不受影响 (守红线: 不破坏既有功能)。
  - 命名沿用 OpenAI SDK 习惯 (OPENAI_API_KEY / OPENAI_BASE_URL), 因生产走 OpenAI 兼容 relay;
    模型默认 gpt-image-2 (spike 验证保结构 img2img)。
  - 预算护栏走"张数"硬闸 (relay 按 token 计费但 $/token 未知, 张数稳妥可控); token 仅计量。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _default_dir(*parts: str) -> str:
    """默认目录推导 (容器恒由 env 显式指定, 此处仅未设 env 时的防御回退)。"""
    here = Path(__file__).resolve()
    try:
        root = here.parents[3]  # apps/api/aigc/config.py -> repo 根
    except IndexError:
        root = here.parent
    return str(root.joinpath(*parts))


def _int(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, "") or default)
    except ValueError:
        return default


def _float(env: str, default: float) -> float:
    """容错解析 (空串/非数字回退默认), 防运维误配让 import 期 get_settings() 崩。"""
    try:
        return float(os.environ.get(env, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    provider: str
    base_url: str
    api_key: str
    model: str
    proxy: str | None
    request_timeout_s: float
    artifacts_dir: str
    uploads_dir: str
    max_images_per_project: int
    daily_image_cap: int

    @property
    def ai_enabled(self) -> bool:
        """凭据齐全才启用 AI; 否则 AI 端点 503, 主服务不受影响。"""
        return bool(self.api_key and self.base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        provider=os.environ.get("IMAGE_PROVIDER", "openai"),
        base_url=os.environ.get("OPENAI_BASE_URL", "").rstrip("/"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("IMAGE_MODEL", "gpt-image-2"),
        # httpx 出网代理 (国内 VPS -> OpenAI 兼容 relay; relay 为 .cn 时通常无需)。
        proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY") or None,
        request_timeout_s=_float("AI_REQUEST_TIMEOUT_S", 300.0),
        artifacts_dir=os.environ.get("ARTIFACTS_DIR", _default_dir("artifacts")),
        uploads_dir=os.environ.get("UPLOADS_DIR", _default_dir("data", "uploads")),
        max_images_per_project=_int("AI_MAX_IMAGES_PER_PROJECT", 200),
        daily_image_cap=_int("AI_DAILY_IMAGE_CAP", 500),
    )
