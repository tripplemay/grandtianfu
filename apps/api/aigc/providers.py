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
import time
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


def _data_uri(png: bytes) -> str:
    """图字节 -> base64 data URI (fal 支持 URL / data URI / storage 上传三选一)。"""
    _ext, mime = _sniff_image(png)
    return f"data:{mime};base64,{base64.b64encode(png).decode()}"


class FalImageProvider:
    """fal.ai flux-general/inpainting 客户端 (异步队列)。路线A 几何锁定实拍生成。

    与 OpenAIImageProvider 并存: 第7步实拍走此 provider —— init(空房照)+mask(家具footprint)
    +可选 ControlNet(depth) 硬约束落位; 第5步轴测仍走 OpenAI edits。缺 FAL_KEY 时 inpaint 抛
    ProviderError (调用方先查 settings.fal_enabled)。队列流程: submit -> 轮询 status -> 取结果。
    """

    def __init__(self, settings: Settings):
        self._s = settings
        # 可选计量回调 (fal 按百万像素计费, 无 token; 回调收到 {width,height})。
        self.on_usage = None

    def inpaint(
        self,
        prompt: str,
        init_png: bytes,
        mask_png: bytes,
        *,
        controlnets: list | None = None,
        size: tuple[int, int] | None = None,
        strength: float = 0.9,
        steps: int = 30,
    ) -> ImageResult:
        """空房照(init)+ mask 区 -> 在 mask 内按 prompt/ControlNet 生成家具, mask 外像素级保留。"""
        if not self._s.fal_key:
            raise ProviderError("fal 未配置 (缺 FAL_KEY)")
        _sniff_image(init_png)  # 非图字节早拒 (与 OpenAI edit 同一道防线)
        _sniff_image(mask_png)
        body: dict = {
            "prompt": prompt,
            "image_url": _data_uri(init_png),
            "mask_url": _data_uri(mask_png),
            "strength": strength,
            "num_inference_steps": steps,
        }
        if size:
            body["image_size"] = {"width": int(size[0]), "height": int(size[1])}
        if controlnets:
            body["controlnets"] = controlnets
        headers = {"Authorization": f"Key {self._s.fal_key}"}
        submit_url = f"{self._s.fal_queue_url}/{self._s.fal_inpaint_model}"
        try:
            with httpx.Client(
                timeout=self._s.request_timeout_s, proxy=self._s.proxy
            ) as client:
                r = client.post(submit_url, headers=headers, json=body)
                if r.status_code >= 400:  # 2xx 都算受理 (fal 队列提交返回 200/202 Accepted)
                    raise ProviderError(
                        f"fal submit 返回 {r.status_code}",
                        status=r.status_code,
                        body=r.text[:1000],
                    )
                q = r.json() or {}
                status_url, response_url = q.get("status_url"), q.get("response_url")
                if not status_url or not response_url:
                    raise ProviderError(
                        "fal submit 响应缺 status_url/response_url", body=str(q)[:1000]
                    )
                for _ in range(max(1, self._s.fal_poll_max)):
                    s = client.get(status_url, headers=headers)
                    if s.status_code >= 400:  # 202 = 仍在处理 (继续轮询); 只有 4xx/5xx 才是错误
                        raise ProviderError(
                            f"fal status {s.status_code}", status=s.status_code, body=s.text[:500]
                        )
                    try:
                        st = (s.json() or {}).get("status")
                    except ValueError:  # 202 可能无 JSON 体
                        st = None
                    if st == "COMPLETED":
                        break
                    if st in ("FAILED", "ERROR"):
                        raise ProviderError("fal 生成失败", body=str(s.json())[:1000])
                    time.sleep(self._s.fal_poll_interval_s)
                else:
                    raise ProviderError("fal 轮询超时")
                res = client.get(response_url, headers=headers)
                if res.status_code != 200:
                    raise ProviderError(
                        f"fal result {res.status_code}", status=res.status_code, body=res.text[:500]
                    )
                payload = res.json() or {}
                images = payload.get("images") or []
                if not images or not images[0].get("url"):
                    raise ProviderError("fal 响应无图像", body=str(payload)[:1000])
                img = images[0]
                dl = client.get(img["url"])
                if dl.status_code != 200:
                    raise ProviderError(f"fal 下载图 {dl.status_code}", status=dl.status_code)
                data = dl.content
        except httpx.HTTPError as exc:
            raise ProviderError(f"fal 请求失败: {exc}") from exc
        usage = {"width": img.get("width"), "height": img.get("height")}
        if self.on_usage:
            try:
                self.on_usage(usage)
            except Exception:  # noqa: BLE001 - 计量失败不阻断生成
                pass
        return ImageResult(
            data=data,
            mime=img.get("content_type") or "image/png",
            usage=usage,
            model=self._s.fal_inpaint_model,
        )


def get_fal_provider(settings: Settings) -> FalImageProvider:
    """fal provider 工厂 (第7步几何锁定用; 缺 FAL_KEY 时 inpaint 抛 ProviderError)。"""
    return FalImageProvider(settings)
