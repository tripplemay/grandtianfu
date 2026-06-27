# -*- coding: utf-8 -*-
"""阅天府软装 — 最小 FastAPI 后端 (Phase 0 walking skeleton)。

引擎接入: import floorplan_core (已 pip install -e packages/floorplan_core), 单一真源。
活几何数据目录由 DATA_DIR(env) 指定, 默认基于 __file__ 相对推导到 轴测图POC/。
"""
import json
import os
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

from floorplan_core import geometry  # 引擎库 (geometry.load/derive/validate 单一真源)

# 活几何数据目录: 默认 = <repo>/轴测图POC (apps/api/main.py 上溯两级到 repo 根)。
DATA_DIR = os.environ.get(
    "DATA_DIR",
    str(Path(__file__).resolve().parents[2] / "轴测图POC"),
)

HOUSE = os.environ.get("HOUSE", "D")

app = FastAPI(title="阅天府软装 API", version="0.0.1")


def _geom_path(house: str) -> Path:
    return Path(DATA_DIR) / f"geometry-{house}户型.json"


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
