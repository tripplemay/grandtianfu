# -*- coding: utf-8 -*-
"""让 `import main` / `import aigc.*` 定位到 apps/api (tests -> apps/api)。"""
import os
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

# 共享 fixture 再导出 (canonical pytest 模式): client_fal (D 户型 tmp 沙箱 + relay/fal 替身)
# 定义在 test_render_real_geometry, 供 test_calibration_dry_run 等标定相关模块复用。
from test_render_real_geometry import client_fal  # noqa: E402,F401
