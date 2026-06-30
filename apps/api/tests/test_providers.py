# -*- coding: utf-8 -*-
"""OpenAI 兼容 provider: 单/多图字段名、b64 解码、usage 解析、错误映射。

httpx 被替身拦截 (不发真网络): 断言 multipart 字段、解析路径、异常类型。
"""
import base64
import json

import pytest

import aigc.providers as providers
from aigc.config import Settings
from aigc.errors import ProviderError
from aigc.providers import OpenAIImageProvider


def _settings():
    return Settings(
        provider="openai", base_url="https://relay/v1", api_key="sk-x", model="gpt-image-2",
        proxy=None, request_timeout_s=300.0, artifacts_dir="/tmp/a", uploads_dir="/tmp/u",
        max_images_per_project=200, daily_image_cap=500,
    )


class _FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    captured = {}
    resp = None

    def __init__(self, **kw):
        _FakeClient.init_kw = kw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, data=None, files=None, json=None):
        _FakeClient.captured = {
            "url": url,
            "headers": headers,
            "data": data,
            "files": files,
            "json": json,
        }
        return _FakeClient.resp


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(providers.httpx, "Client", _FakeClient)
    return _FakeClient


def _ok_resp(raw=b"PNGBYTES"):
    return _FakeResp(200, {"data": [{"b64_json": base64.b64encode(raw).decode()}],
                           "usage": {"total_tokens": 4242}})


def test_single_image_uses_image_field(patched):
    patched.resp = _ok_resp(b"AAA")
    res = OpenAIImageProvider(_settings()).edit("prompt", [b"img"])
    assert patched.captured["files"][0][0] == "image"
    assert patched.captured["url"] == "https://relay/v1/images/edits"
    assert patched.captured["data"]["model"] == "gpt-image-2"
    assert res.data == b"AAA"
    assert res.usage["total_tokens"] == 4242


def test_multi_image_uses_image_array_field(patched):
    patched.resp = _ok_resp()
    OpenAIImageProvider(_settings()).edit("p", [b"a", b"b"])
    names = [f[0] for f in patched.captured["files"]]
    assert names == ["image[]", "image[]"]


def test_empty_images_raises(patched):
    with pytest.raises(ProviderError):
        OpenAIImageProvider(_settings()).edit("p", [])


def test_non_200_raises_with_status(patched):
    patched.resp = _FakeResp(429, text="rate limited")
    with pytest.raises(ProviderError) as ei:
        OpenAIImageProvider(_settings()).edit("p", [b"x"])
    assert ei.value.status == 429


def test_missing_b64_raises(patched):
    patched.resp = _FakeResp(200, {"data": [{}]})
    with pytest.raises(ProviderError):
        OpenAIImageProvider(_settings()).edit("p", [b"x"])


def test_factory_unknown_provider():
    from aigc.providers import get_provider
    with pytest.raises(ProviderError):
        get_provider(Settings(
            provider="midjourney", base_url="x", api_key="k", model="m", proxy=None,
            request_timeout_s=1.0, artifacts_dir="/tmp", uploads_dir="/tmp",
            max_images_per_project=1, daily_image_cap=1,
        ))


def test_chat_json_posts_json_mode_request(patched):
    patched.resp = _FakeResp(
        200,
        {
            "choices": [
                {"message": {"content": json.dumps({"rooms": [{"room_id": "r1"}]})}}
            ],
            "usage": {"total_tokens": 123},
        },
    )

    result = OpenAIImageProvider(_settings()).chat_json(
        [{"role": "user", "content": "pick furniture"}],
        model="gpt-5.5",
        temperature=0.1,
    )

    assert result == {"rooms": [{"room_id": "r1"}]}
    assert patched.captured["url"] == "https://relay/v1/chat/completions"
    payload = patched.captured["json"]
    assert payload["model"] == "gpt-5.5"
    assert payload["messages"][0]["content"] == "pick furniture"
    assert payload["temperature"] == 0.1
    assert payload["response_format"] == {"type": "json_object"}


def test_chat_json_non_200_raises_provider_error(patched):
    patched.resp = _FakeResp(500, text="bad gateway")

    with pytest.raises(ProviderError) as ei:
        OpenAIImageProvider(_settings()).chat_json([{"role": "user", "content": "x"}])

    assert ei.value.status == 500


def test_chat_json_malformed_json_raises_provider_error(patched):
    patched.resp = _FakeResp(200, {"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(ProviderError):
        OpenAIImageProvider(_settings()).chat_json([{"role": "user", "content": "x"}])
