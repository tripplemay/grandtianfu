# -*- coding: utf-8 -*-
"""fal FalImageProvider: 队列 inpaint 流程 / body 字段 / 轮询 / 错误映射。

httpx 被替身拦截 (不发真网络): 断言 submit body、data URI、轮询次数、异常类型。
"""

import aigc.providers as providers
import pytest
from aigc.config import Settings
from aigc.errors import ProviderError
from aigc.providers import FalImageProvider

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 8
_JPG = b"\xff\xd8\xff\xe0" + b"0" * 8


def _settings(fal_key="fal-key-x"):
    return Settings(
        provider="openai",
        base_url="https://relay/v1",
        api_key="sk-x",
        model="gpt-image-2",
        proxy=None,
        request_timeout_s=300.0,
        artifacts_dir="/tmp/a",
        uploads_dir="/tmp/u",
        max_images_per_project=200,
        daily_image_cap=500,
        fal_key=fal_key,
        fal_queue_url="https://queue.fal.run",
        fal_inpaint_model="fal-ai/flux-general/inpainting",
        fal_poll_interval_s=0.0,
        fal_poll_max=5,
    )


class _Resp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FalClient:
    def __init__(self, **kw):
        _FalClient.init_kw = kw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None, **kw):
        _FalClient.calls.append(("POST", url, headers, json))
        return _Resp(_FalClient.submit_status, _FalClient.submit_payload)

    def get(self, url, headers=None, **kw):
        _FalClient.calls.append(("GET", url, headers))
        if url.endswith("/status"):
            i = min(_FalClient.status_i, len(_FalClient.status_seq) - 1)
            _FalClient.status_i += 1
            return _Resp(_FalClient.status_http, {"status": _FalClient.status_seq[i]})
        if "fal.media" in url:
            return _Resp(200, content=_FalClient.img_bytes)
        return _Resp(200, _FalClient.result_payload)  # response_url


@pytest.fixture
def falc(monkeypatch):
    _FalClient.calls = []
    _FalClient.status_i = 0
    _FalClient.status_http = 200
    _FalClient.status_seq = ["COMPLETED"]
    _FalClient.submit_status = 200
    _FalClient.submit_payload = {
        "status": "IN_QUEUE",
        "status_url": "https://queue.fal.run/req/status",
        "response_url": "https://queue.fal.run/req",
    }
    _FalClient.result_payload = {
        "images": [
            {
                "url": "https://v3.fal.media/x.png",
                "width": 1536,
                "height": 1024,
                "content_type": "image/png",
            }
        ]
    }
    _FalClient.img_bytes = b"FALIMG"
    monkeypatch.setattr(providers.httpx, "Client", _FalClient)
    return _FalClient


def test_inpaint_queue_flow_returns_image(falc):
    res = FalImageProvider(_settings()).inpaint("p", _JPG, _PNG, size=(1536, 1024))
    assert res.data == b"FALIMG"
    assert res.model == "fal-ai/flux-general/inpainting"
    post = next(c for c in falc.calls if c[0] == "POST")
    assert post[1] == "https://queue.fal.run/fal-ai/flux-general/inpainting"
    assert post[2]["Authorization"] == "Key fal-key-x"
    body = post[3]
    assert body["image_url"].startswith("data:image/jpeg;base64,")  # 空房照 jpg
    assert body["mask_url"].startswith("data:image/png;base64,")  # mask png
    assert body["image_size"] == {"width": 1536, "height": 1024}


def test_inpaint_polls_until_completed(falc):
    falc.status_seq = ["IN_QUEUE", "IN_PROGRESS", "COMPLETED"]
    res = FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)
    assert res.data == b"FALIMG"
    polls = [c for c in falc.calls if c[0] == "GET" and c[1].endswith("/status")]
    assert len(polls) == 3


def test_inpaint_controlnets_passed(falc):
    cn = [{"path": "flux-depth", "control_image_url": "data:x", "conditioning_scale": 0.6}]
    FalImageProvider(_settings()).inpaint("p", _JPG, _PNG, controlnets=cn)
    body = next(c for c in falc.calls if c[0] == "POST")[3]
    assert body["controlnets"] == cn


def test_inpaint_missing_fal_key_raises(falc):
    with pytest.raises(ProviderError):
        FalImageProvider(_settings(fal_key="")).inpaint("p", _JPG, _PNG)


def test_inpaint_failed_status_raises(falc):
    falc.status_seq = ["FAILED"]
    with pytest.raises(ProviderError):
        FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)


def test_inpaint_submit_non200_raises(falc):
    falc.submit_status = 500
    falc.submit_payload = None
    with pytest.raises(ProviderError) as ei:
        FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)
    assert ei.value.status == 500


def test_inpaint_accepts_202_submit(falc):
    """fal 队列受理返回 202 Accepted (不是 200), 须视为正常继续轮询。"""
    falc.submit_status = 202
    res = FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)
    assert res.data == b"FALIMG"


def test_inpaint_poll_status_202_continues(falc):
    """fal status 端点未完成时返回 202 (非错误), 须继续轮询到 COMPLETED。"""
    falc.status_http = 202
    falc.status_seq = ["IN_PROGRESS", "COMPLETED"]
    res = FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)
    assert res.data == b"FALIMG"


def test_inpaint_poll_timeout_raises(falc):
    falc.status_seq = ["IN_QUEUE"]
    with pytest.raises(ProviderError):
        FalImageProvider(_settings()).inpaint("p", _JPG, _PNG)


def test_inpaint_non_image_bytes_raises(falc):
    with pytest.raises(ProviderError):
        FalImageProvider(_settings()).inpaint("p", b"not-an-image", _PNG)


def test_edit_two_image_flow(falc):
    """几何锁定形体提质主路径: 双图 (空房照+彩盒标注) 指令编辑, 默认 nano-banana。"""
    res = FalImageProvider(_settings()).edit("furnish per boxes", [_JPG, _PNG])
    assert res.data == b"FALIMG"
    assert res.model == "fal-ai/nano-banana/edit"
    post = next(c for c in falc.calls if c[0] == "POST")
    assert post[1] == "https://queue.fal.run/fal-ai/nano-banana/edit"
    body = post[3]
    assert len(body["image_urls"]) == 2
    assert body["image_urls"][0].startswith("data:image/jpeg;base64,")  # 空房照
    assert body["image_urls"][1].startswith("data:image/png;base64,")  # 标注图
    assert body["num_images"] == 1
    assert body["prompt"] == "furnish per boxes"


def test_edit_model_override_and_extra(falc):
    FalImageProvider(_settings()).edit(
        "p", [_PNG], model="fal-ai/nano-banana-pro/edit", extra={"output_resolution": "2K"}
    )
    post = next(c for c in falc.calls if c[0] == "POST")
    assert post[1] == "https://queue.fal.run/fal-ai/nano-banana-pro/edit"
    assert post[3]["output_resolution"] == "2K"


def test_edit_missing_fal_key_raises(falc):
    with pytest.raises(ProviderError):
        FalImageProvider(_settings(fal_key="")).edit("p", [_PNG])


def test_edit_empty_images_raises(falc):
    with pytest.raises(ProviderError):
        FalImageProvider(_settings()).edit("p", [])


def test_edit_non_image_bytes_raises(falc):
    with pytest.raises(ProviderError):
        FalImageProvider(_settings()).edit("p", [b"not-an-image"])


def test_fal_enabled_flag():
    assert _settings().fal_enabled is True
    assert _settings(fal_key="").fal_enabled is False
