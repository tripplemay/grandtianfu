# -*- coding: utf-8 -*-
"""AI 子系统配置: 全部来自环境变量, 启动期一次性读取。

设计要点:
  - **AI 凭据缺失不让整服务崩** (现有 geometry/render 端点必须照常)。无 OPENAI_API_KEY 时
    ai_enabled=False, AI 端点返回 503, 其余不受影响 (守红线: 不破坏既有功能)。
  - 命名沿用 OpenAI SDK 习惯 (OPENAI_API_KEY / OPENAI_BASE_URL), 因生产走 OpenAI 兼容 relay;
    图像模型默认 gpt-image-2 (spike 验证保结构 img2img); chat JSON 规划走独立 CHAT_MODEL。
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
    chat_model: str = "gpt-5.5"
    # AI 摆家具 (chat) 每日次数闸: chat 按 token 计费但 $/token 未知, 次数硬闸稳妥可控。
    furnish_daily_cap: int = 200
    # fal.ai 几何锁定实拍生成 (路线A): flux-general/inpainting 异步队列。缺 fal_key -> fal_enabled=False。
    fal_key: str = ""
    fal_queue_url: str = "https://queue.fal.run"
    fal_inpaint_model: str = "fal-ai/flux-general/inpainting"
    # 家具形体提质: 指令编辑模型 (双图: 空房照+彩盒标注) 画立体家具; inpaint 平 mask 只出矮物。
    fal_edit_model: str = "fal-ai/nano-banana/edit"
    fal_poll_interval_s: float = 3.0
    fal_poll_max: int = 90

    @property
    def ai_enabled(self) -> bool:
        """凭据齐全才启用 AI; 否则 AI 端点 503, 主服务不受影响。"""
        return bool(self.api_key and self.base_url)

    @property
    def fal_enabled(self) -> bool:
        """fal 几何锁定生成需单独的 fal_key; 缺则回退旧生成路径, 不崩主服务。"""
        return bool(self.fal_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        provider=os.environ.get("IMAGE_PROVIDER", "openai"),
        base_url=os.environ.get("OPENAI_BASE_URL", "").rstrip("/"),
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("IMAGE_MODEL", "gpt-image-2"),
        chat_model=os.environ.get("CHAT_MODEL") or "gpt-5.5",
        # httpx 出网代理 (国内 VPS -> OpenAI 兼容 relay; relay 为 .cn 时通常无需)。
        proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY") or None,
        request_timeout_s=_float("AI_REQUEST_TIMEOUT_S", 300.0),
        artifacts_dir=os.environ.get("ARTIFACTS_DIR", _default_dir("artifacts")),
        uploads_dir=os.environ.get("UPLOADS_DIR", _default_dir("data", "uploads")),
        max_images_per_project=_int("AI_MAX_IMAGES_PER_PROJECT", 200),
        daily_image_cap=_int("AI_DAILY_IMAGE_CAP", 500),
        furnish_daily_cap=_int("AI_FURNISH_DAILY_CAP", 200),
        fal_key=os.environ.get("FAL_KEY", ""),
        fal_queue_url=os.environ.get("FAL_QUEUE_URL", "https://queue.fal.run").rstrip("/"),
        fal_inpaint_model=os.environ.get("FAL_INPAINT_MODEL", "fal-ai/flux-general/inpainting"),
        fal_edit_model=os.environ.get("FAL_EDIT_MODEL", "fal-ai/nano-banana/edit"),
        fal_poll_interval_s=_float("FAL_POLL_INTERVAL_S", 3.0),
        fal_poll_max=_int("FAL_POLL_MAX", 90),
    )
