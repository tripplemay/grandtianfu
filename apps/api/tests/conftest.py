# -*- coding: utf-8 -*-
"""让 `import main` / `import aigc.*` 定位到 apps/api (tests -> apps/api)。"""
import os
import sys

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
