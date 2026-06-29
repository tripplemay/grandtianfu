# -*- coding: utf-8 -*-
"""图像生成 provider 抽象 + OpenAI 兼容实现 (生产 relay)。

spike 实测 (2026-06-29): POST {base}/images/edits multipart —— 单图 `image=@file`,
多图 `image[]=@file`; 返回 data[0].b64_json + usage(image/text token 计量)。
本实现单/多图统一: 第5步单图 (轴测底图), 第7步多图 (空房照 + 轴侧方案参考)。
provider 抽象保留, 后续可挂 fal/Gemini 而不动调用方。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import ProviderError


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    usage: dict
    model: str


class ImageProvider(Protocol):
    def edit(
        self,
        prompt: str,
        images: list[bytes],
        *,
        size: str = "1536x1024",
        model: str | None = None,
    ) -> ImageResult:
        """以 1+ 张输入图为条件做图像编辑 (img2img), 返回单张结果。"""
        ...


class OpenAIImageProvider:
    """OpenAI 兼容 /images/edits 客户端 (httpx, 支持出网代理)。"""

    def __init__(self, settings: Settings):
        self._s = settings

    def edit(
        self,
        prompt: str,
        images: list[bytes],
        *,
        size: str = "1536x1024",
        model: str | None = None,
    ) -> ImageResult:
        if not images:
            raise ProviderError("edit() 需要至少一张输入图")
        model = model or self._s.model
        # 单图用 `image`、多图用 `image[]` (relay 兼容 OpenAI 约定; spike 验证)。
        field = "image" if len(images) == 1 else "image[]"
        files = [(field, (f"image{i}.png", img, "image/png")) for i, img in enumerate(images)]
        data = {"model": model, "prompt": prompt, "size": size}
        url = f"{self._s.base_url}/images/edits"
        headers = {"Authorization": f"Bearer {self._s.api_key}"}
        try:
            with httpx.Client(timeout=self._s.request_timeout_s, proxy=self._s.proxy) as client:
                resp = client.post(url, headers=headers, data=data, files=files)
        except httpx.HTTPError as exc:  # 网络/超时
            raise ProviderError(f"image edit 请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(
                f"provider 返回 {resp.status_code}", status=resp.status_code, body=resp.text[:1000]
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderError("provider 返回非 JSON", body=resp.text[:1000]) from exc
        items = payload.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise ProviderError("provider 响应无图像 (无 b64_json)", body=str(payload)[:1000])
        return ImageResult(
            data=base64.b64decode(items[0]["b64_json"]),
            mime="image/png",
            usage=payload.get("usage", {}) or {},
            model=model,
        )


def get_provider(settings: Settings) -> ImageProvider:
    """provider 工厂 (按 IMAGE_PROVIDER 选实现; 当前仅 OpenAI 兼容)。"""
    if settings.provider in ("openai", "gpt-image", ""):
        return OpenAIImageProvider(settings)
    raise ProviderError(f"未知 IMAGE_PROVIDER: {settings.provider!r}")
