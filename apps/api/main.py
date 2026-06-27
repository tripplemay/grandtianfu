# -*- coding: utf-8 -*-
"""阅天府软装 — 最小 FastAPI 后端 (Phase 0 walking skeleton)。

红线: 原样复用 轴测图POC/ 下现有引擎, 不搬移任何文件。
本服务通过 ENGINE_DIR 环境变量 + sys.path.insert 在原地 import geometry。
"""
import json
import os
import sys
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

# --------------------------------------------------------------------------- #
#  引擎接入: ENGINE_DIR(env) -> sys.path.insert -> import geometry(原地)
# --------------------------------------------------------------------------- #
ENGINE_DIR = os.environ.get(
    "ENGINE_DIR",
    "/Users/yixingzhou/project/grandtianfu/轴测图POC",
)
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

import geometry  # noqa: E402  (原引擎, geometry.load/derive/validate 单一真源)

HOUSE = os.environ.get("HOUSE", "D")

app = FastAPI(title="阅天府软装 API", version="0.0.1")


def _geom_path(house: str) -> Path:
    return Path(ENGINE_DIR) / f"geometry-{house}户型.json"


# --------------------------------------------------------------------------- #
#  路由
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/projects/{house}/geometry")
def get_geometry(house: str):
    path = _geom_path(house)
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"geometry for house {house!r} not found"},
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# derive 是 GIL 下同步 CPU 纯函数: 用 def(非 async def) 让 FastAPI 自动丢线程池,
# 避免阻塞事件循环 (对抗 #14)。FastAPI 在 async 层解析 body, 再把本函数派发到线程池。
@app.post("/api/derive")
def derive(G: dict = Body(...)):
    try:
        res = geometry.derive(G)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
    # 与 serve.py /derive 字段对齐 (parity 基准)
    return {
        "walls": res.get("walls", []),
        "doors": res.get("doors", []),
        "windows": res.get("windows", []),
        "dims": res.get("dims", {}),
        "conflicts": res.get("conflicts", []),
        "warns": res.get("warns", []),
        "_walls_raw": res.get("_walls_raw", []),
    }
