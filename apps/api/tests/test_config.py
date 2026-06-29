# -*- coding: utf-8 -*-
"""配置: ai_enabled 判定、容错解析 (空/非法 env 不崩 import)、凭据缺失降级。"""
from aigc.config import Settings, _float, _int, get_settings


def _mk(**over):
    base = dict(
        provider="openai", base_url="https://x/v1", api_key="k", model="m", proxy=None,
        request_timeout_s=1.0, artifacts_dir="/tmp", uploads_dir="/tmp",
        max_images_per_project=1, daily_image_cap=1,
    )
    base.update(over)
    return Settings(**base)


def test_ai_enabled_requires_key_and_base():
    assert _mk(api_key="k", base_url="https://x").ai_enabled is True
    assert _mk(api_key="", base_url="https://x").ai_enabled is False
    assert _mk(api_key="k", base_url="").ai_enabled is False


def test_float_fallback_on_bad_env(monkeypatch):
    monkeypatch.setenv("X_TO", "")  # 空串曾让裸 float() 抛 ValueError
    assert _float("X_TO", 300.0) == 300.0
    monkeypatch.setenv("X_TO", "abc")
    assert _float("X_TO", 300.0) == 300.0
    monkeypatch.setenv("X_TO", "12.5")
    assert _float("X_TO", 300.0) == 12.5


def test_int_fallback_on_bad_env(monkeypatch):
    monkeypatch.setenv("X_N", "nope")
    assert _int("X_N", 7) == 7
    monkeypatch.setenv("X_N", "9")
    assert _int("X_N", 7) == 9


def test_get_settings_tolerates_empty_timeout_env(monkeypatch):
    """运维误配 AI_REQUEST_TIMEOUT_S= (空串) 不应让 import 期 get_settings() 崩。"""
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_S", "")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.request_timeout_s == 300.0
        assert s.ai_enabled is False  # 无 key -> 降级, 不崩
    finally:
        get_settings.cache_clear()
