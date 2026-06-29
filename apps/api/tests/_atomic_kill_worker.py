# -*- coding: utf-8 -*-
"""原子写崩溃测试的子进程 worker: 对目标文件无限循环原子写大 payload。

父测试随机时刻 SIGKILL 本进程, 验证 os.replace 的原子性 —— 任何时刻被 -9 杀死后,
目标文件要么是某次完整旧版、要么是某次完整新版, 永不出现被截断的半截 JSON。
"""
import os
import sys
from pathlib import Path

# 让 `import main` 可定位到 apps/api/main.py (tests -> apps/api)。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _atomic_write_json  # noqa: E402

if __name__ == "__main__":
    target = Path(sys.argv[1])
    i = 0
    while True:
        i += 1
        # 20KB padding 拉长写窗口, 提高"恰在写盘中途被杀"的命中率。
        _atomic_write_json(target, {"v": i, "pad": "中文padding" * 2000}, indent=2)
