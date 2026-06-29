# -*- coding: utf-8 -*-
"""阶段0 验收: main._atomic_write_json 原子落盘的崩溃安全 + 字节往返不破。

覆盖:
  1. 字节往返: 输出与旧 open("w")+json.dump(...indent=n) 逐字节一致 (不破基线 SVG/家具 md5)。
  2. .bak 单步回退: 覆盖写后 .bak == 上一版, 主文件 == 新版。
  3. 异常中断 (os.replace 抛错=模拟 commit 前崩溃): 主文件保持旧版完整, 绝不被截断。
  4. 真实 SIGKILL: 子进程不停原子写, 父进程随机时刻 kill -9; 主文件若存在必是完整可解析 JSON。
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# 让 `import main` 定位到 apps/api/main.py (tests -> apps/api)。
API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import main  # noqa: E402
from main import _atomic_write_json  # noqa: E402


def test_byte_identical_to_legacy_dump(tmp_path):
    """原子写字节 == 旧 json.dump(ensure_ascii=False, indent=2) (含中文, 无末换行)。"""
    obj = {"meta": {"name": "阅天府D户型"}, "rooms": [1, 2, 3], "nested": {"k": "值"}}
    p = tmp_path / "geometry.json"
    _atomic_write_json(p, obj, indent=2)
    got = p.read_bytes()
    expect = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    assert got == expect


def test_byte_identical_furniture_indent1(tmp_path):
    """家具 indent=1 路径字节一致 (GET->原样 POST 回存 md5 不变)。"""
    arr = [{"room_id": "r1", "dx": 10, "dy": -5}, {"room_id": "r2", "dx": 0, "dy": 0}]
    p = tmp_path / "furniture.json"
    _atomic_write_json(p, arr, indent=1)
    assert p.read_bytes() == json.dumps(arr, ensure_ascii=False, indent=1).encode("utf-8")


def test_keeps_bak_for_single_step_rollback(tmp_path):
    """覆盖写: .bak 留上一版, 主文件为新版 (单步回退可用)。"""
    p = tmp_path / "geometry.json"
    _atomic_write_json(p, {"v": 1}, indent=2)
    _atomic_write_json(p, {"v": 2}, indent=2)
    bak = p.with_name(p.name + ".bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8"))["v"] == 1
    assert json.loads(p.read_text(encoding="utf-8"))["v"] == 2


def test_crash_before_commit_keeps_old_intact(tmp_path, monkeypatch):
    """模拟 commit 前崩溃 (os.replace 抛错): 主文件仍是完整旧版, 字节不变, 未被截断。"""
    p = tmp_path / "geometry.json"
    _atomic_write_json(p, {"v": "OLD"}, indent=2)
    old_bytes = p.read_bytes()

    def _boom(*_a, **_k):
        raise OSError("simulated crash before atomic commit")

    monkeypatch.setattr(main.os, "replace", _boom)
    with pytest.raises(OSError):
        _atomic_write_json(p, {"v": "NEW-" + "x" * 50000}, indent=2)

    # 替换失败 -> 旧版应原封不动、逐字节一致、可完整解析。
    assert p.read_bytes() == old_bytes
    assert json.loads(p.read_text(encoding="utf-8"))["v"] == "OLD"


def test_sigkill_never_truncates_file(tmp_path):
    """真实 kill -9: 子进程不停原子写, 父随机时刻杀; 主文件若存在必是完整可解析 JSON。"""
    target = tmp_path / "geometry.json"
    worker = Path(__file__).parent / "_atomic_kill_worker.py"
    saw_valid = False
    for rnd in range(8):
        proc = subprocess.Popen([sys.executable, str(worker), str(target)])
        # worker 启动 (import main+floorplan_core) 约 0.2s, 故基线 0.4s 让其先写若干轮, 再随机延后杀,
        # 命中"写盘中途/replace 前后"窗口。
        time.sleep(0.4 + 0.05 * rnd)
        proc.send_signal(signal.SIGKILL)
        proc.wait()
        if target.exists():
            # 关键断言: 被 -9 后文件必须完整可解析 (绝不半截 JSON)。
            data = json.loads(target.read_text(encoding="utf-8"))
            assert isinstance(data.get("v"), int) and data["v"] >= 1
            saw_valid = True
    assert saw_valid, "子进程从未成功写出可解析文件 (环境异常)"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
