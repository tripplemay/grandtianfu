# -*- coding: utf-8 -*-
"""图像生成 provider 抽象 + OpenAI 兼容实现 (生产 relay)。

spike 实测 (2026-06-29): POST {base}/images/edits multipart —— 单图 `image=@file`,
多图 `image[]=@file`; 返回 data[0].b64_json + usage(image/text token 计量)。
本实现单/多图统一: 第5步单图 (轴测底图), 第7步多图 (空房照 + 轴侧方案参考)。
provider 抽象保留, 后续可挂 fal/Gemini 而不动调用方。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import ProviderError


# img2img 参考图硬上限 (gpt-image-2 relay 约定; P2 材质C 多图注入的闸门)。
# 调用方须自行裁到该数; provider 再做一道防御, 超限直接失败而非静默丢图。
MAX_EDIT_IMAGES = 4


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

    def chat_json(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Chat completions JSON-object mode, parsed into a dict."""
        ...


def _sniff_image(data: bytes) -> tuple[str, str]:
    """按 magic bytes 识别图像类型 -> (ext, mime); 未识别抛 ProviderError。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise ProviderError("输入图字节不是可识别的 PNG/JPEG/WEBP")


class OpenAIImageProvider:
    """OpenAI 兼容 images/chat 客户端 (httpx, 支持出网代理)。"""

    def __init__(self, settings: Settings):
        self._s = settings
        # 可选 token 计量回调 (调用方可挂 budget.record_tokens); chat_json 成功后回调 usage。
        self.on_usage = None

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
        if len(images) > MAX_EDIT_IMAGES:
            raise ProviderError(
                f"edit() 参考图 {len(images)} 张超上限 {MAX_EDIT_IMAGES} (调用方须先裁剪)"
            )
        model = model or self._s.model
        # 单图用 `image`、多图用 `image[]` (relay 兼容 OpenAI 约定; spike 验证)。
        field = "image" if len(images) == 1 else "image[]"
        # 按 magic bytes 判型设文件名/mime (第7步空房照可能是 jpg/webp, 硬标 png 属格式错配;
        # 未识别字节直接拒绝 —— 顺带补上「非图字节送 provider」的防线)。
        files = []
        for i, img in enumerate(images):
            ext, mime = _sniff_image(img)
            files.append((field, (f"image{i}.{ext}", img, mime)))
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

    def chat_json(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        model = model or self._s.chat_model
        url = f"{self._s.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._s.api_key}"}
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=self._s.request_timeout_s, proxy=self._s.proxy) as client:
                resp = client.post(url, headers=headers, json=data)
        except httpx.HTTPError as exc:
            raise ProviderError(f"chat 请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(
                f"provider 返回 {resp.status_code}", status=resp.status_code, body=resp.text[:1000]
            )
        try:
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            body = resp.text[:1000] if hasattr(resp, "text") else str(payload)[:1000]
            raise ProviderError("provider chat JSON 响应无效", body=body) from exc
        if not isinstance(parsed, dict):
            raise ProviderError("provider chat JSON 响应不是对象", body=str(parsed)[:1000])
        # token 计量 (可选回调): 让 LLM 摆家具的用量也进 /api/ai/status 监控。
        usage = payload.get("usage") or {}
        if self.on_usage and usage:
            try:
                self.on_usage(usage)
            except Exception:  # noqa: BLE001 - 计量失败不阻断生成主流程。
                pass
        return parsed


def get_provider(settings: Settings) -> ImageProvider:
    """provider 工厂 (按 IMAGE_PROVIDER 选实现; 当前仅 OpenAI 兼容)。"""
    if settings.provider in ("openai", "gpt-image", ""):
        return OpenAIImageProvider(settings)
    raise ProviderError(f"未知 IMAGE_PROVIDER: {settings.provider!r}")
