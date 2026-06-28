# -*- coding: utf-8 -*-
"""阅天府软装 — 最小 FastAPI 后端 (Phase 0 walking skeleton)。

引擎接入: import floorplan_core (已 pip install -e packages/floorplan_core), 单一真源。
活编辑数据目录由 DATA_DIR(env) 指定, 默认基于 __file__ 相对推导到 data/projects/。
布局: {DATA_DIR}/{house}/geometry.json + {DATA_DIR}/{house}/furniture.json。
活数据已自引擎/红线目录 (轴测图POC) 迁出, 杜绝「测试期 save-geometry 误写红线参照」污染。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse, Response

from floorplan_core import axon, geometry  # 引擎库 (geometry/axon 单一真源)

# 活编辑数据目录: 默认 = <repo>/data/projects (apps/api/main.py 上溯两级到 repo 根)。
DATA_DIR = os.environ.get(
    "DATA_DIR",
    str(Path(__file__).resolve().parents[2] / "data" / "projects"),
)

HOUSE = os.environ.get("HOUSE", "D")

# 红线护栏: GEOM_READONLY 置真时 /save-geometry 拒写 (返回 403), 杜绝冒烟/测试会话
# 把 save-geometry 落盘污染活数据。活数据已迁出红线目录 (data/projects), 此护栏为双保险。
# 默认关 → 生产几何模式行为不变 (不破坏几何模式)。
GEOM_READONLY = os.environ.get("GEOM_READONLY", "").lower() in ("1", "true", "yes")

app = FastAPI(title="阅天府软装 API", version="0.0.1")


def _geom_path(house: str) -> Path:
    return Path(DATA_DIR) / house / "geometry.json"


def _furniture_path(house: str) -> Path:
    return Path(DATA_DIR) / house / "furniture.json"


# 项目 id 安全校验: 仅字母/数字/-/_; 拒 ..、/、绝对路径 (防路径穿越)。
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_project_id(pid: str) -> bool:
    """项目 id 路径安全: 仅 [A-Za-z0-9_-], 非空, 杜绝 ../、绝对路径、分隔符。"""
    return bool(pid) and bool(_PROJECT_ID_RE.match(pid))


# 起步几何 meta: 复用 D 的标定参数 (origin/grid/wall厚/wall_height/canvas_viewbox/eps),
# 保证新项目与红线一致的坐标系/比例。读不到 D 时回退到内置常量 (不阻断新建)。
_FALLBACK_META = {
    "schema_version": 2,
    "mm_per_px": 10,
    "origin": [150, 250],
    "canvas_viewbox": [0, 0, 2200, 1800],
    "wall_thickness_mm": {
        "exterior": 240,
        "demarcation": 200,
        "interior": 140,
        "outdoor": 240,
        "thin": 60,
        "public": 60,
    },
    "wall_height_mm": 1450,
    "grid": 5,
    "eps": 1,
}

_META_COPY_KEYS = (
    "schema_version",
    "mm_per_px",
    "origin",
    "canvas_viewbox",
    "wall_thickness_mm",
    "wall_height_mm",
    "grid",
    "eps",
)


def _starter_meta(name: str | None) -> dict:
    """复制 D 的标定 meta (失败回退内置常量), 可选注入展示名 meta.name。"""
    base = dict(_FALLBACK_META)
    dpath = _geom_path("D")
    if dpath.exists():
        try:
            with dpath.open("r", encoding="utf-8") as fh:
                dmeta = json.load(fh).get("meta", {})
            for k in _META_COPY_KEYS:
                if k in dmeta:
                    base[k] = dmeta[k]
        except Exception:  # noqa: BLE001 — D 读失败不阻断新建, 用回退 meta
            pass
    if name:
        base["name"] = name
    return base


def _starter_geometry(name: str | None) -> dict:
    """最小合法起步几何: 单 interior 房间, 空开洞/自由墙/标注, dims auto。
    须经 geometry.validate 通过且 derive 出墙 (单房 -> 4 面墙)。"""
    return {
        "meta": _starter_meta(name),
        "spaces": {
            "room1": {"category": "interior", "label": "房间", "style": "solid"},
        },
        "rooms": [
            {
                "id": "r1",
                "space": "room1",
                "type": "living",
                "rect": [100, 120, 600, 420],
                "label": {"zh": "房间", "at": [400, 330]},
            },
        ],
        "openings": [],
        "free_walls": [],
        "annotations": [],
        "dims": {
            "auto": True,
            "sides": ["top", "left"],
            "offsets_px": {"top": 60, "left": 60, "right": 60, "bottom": 60},
            "exclude_coords": [],
            "overrides": [],
        },
    }


def _project_summary(pid: str) -> dict | None:
    """读某项目 geometry.json -> {id, name, rooms}; 无 geometry 时返回 None。"""
    gpath = _geom_path(pid)
    if not gpath.exists():
        return None
    try:
        with gpath.open("r", encoding="utf-8") as fh:
            G = json.load(fh)
    except Exception:  # noqa: BLE001 — 单项目损坏不应拖垮整张列表
        return {"id": pid, "name": pid, "rooms": 0}
    meta = G.get("meta", {}) if isinstance(G, dict) else {}
    name = meta.get("name") or pid
    rooms = len(G.get("rooms", [])) if isinstance(G, dict) else 0
    return {"id": pid, "name": name, "rooms": rooms}


# 渲染模式 -> 写盘编码 (与 build.py 落盘一致, 保证 API 字节 == 基线 SVG):
#   plan2d 走 render_plan_2d (历史用 utf-8-sig, 带 BOM);
#   photo/shell 走 render (utf-8, 无 BOM)。
_RENDER_MODES = {"plan2d", "photo", "shell"}


# --------------------------------------------------------------------------- #
#  路由
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# --------------------------------------------------------------------------- #
#  projects CRUD (Stage C 项目台)
# --------------------------------------------------------------------------- #
@app.get("/api/projects")
def list_projects():
    """列出 DATA_DIR 下每个含 geometry.json 的子目录为项目 [{id,name,rooms}]。"""
    root = Path(DATA_DIR)
    out: list[dict] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            summary = _project_summary(child.name)
            if summary is not None:
                out.append(summary)
    return out


@app.post("/api/projects")
def create_project(payload: dict = Body(...)):
    """新建项目: id 路径安全校验, 已存在 409; 写最小合法起步几何 + 空家具。

    起步几何须 geometry.validate 通过且 derive 出墙, 否则 500 并回滚 (不留半成品)。"""
    pid = (payload or {}).get("id")
    name = (payload or {}).get("name")
    if not isinstance(pid, str) or not _safe_project_id(pid):
        return JSONResponse(
            status_code=400,
            content={
                "error": "id 非法: 仅允许字母/数字/-/_, 禁止 .. / 绝对路径",
            },
        )
    if name is not None and not isinstance(name, str):
        return JSONResponse(status_code=400, content={"error": "name 必须为字符串"})

    proj_dir = Path(DATA_DIR) / pid
    if proj_dir.exists():
        return JSONResponse(
            status_code=409,
            content={"error": f"项目 {pid!r} 已存在"},
        )

    G = _starter_geometry(name)
    # 落盘前先校验 + 派生, 确保起步几何可用 (validate 无 ERROR 且 derive 出墙)。
    try:
        issues = geometry.validate(G)
        errors = [msg for level, msg in issues if level == "ERROR"]
        if errors:
            return JSONResponse(
                status_code=500,
                content={"error": "起步几何校验未过", "errors": errors},
            )
        derived = geometry.derive(G)
        if not derived.get("walls"):
            return JSONResponse(
                status_code=500,
                content={"error": "起步几何未派生出墙"},
            )
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})

    try:
        proj_dir.mkdir(parents=True, exist_ok=False)
        with _geom_path(pid).open("w", encoding="utf-8") as fh:
            json.dump(G, fh, ensure_ascii=False, indent=2)
        with _furniture_path(pid).open("w", encoding="utf-8") as fh:
            json.dump([], fh, ensure_ascii=False, indent=1)
    except Exception as exc:  # noqa: BLE001 — 落盘失败回滚半成品目录
        shutil.rmtree(proj_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(status_code=201, content=_project_summary(pid))


@app.delete("/api/projects/{house}")
def delete_project(house: str):
    """删除项目目录 (id 安全校验; 不受 GEOM_READONLY 影响, 仅作 id 防穿越)。"""
    if not _safe_project_id(house):
        return JSONResponse(
            status_code=400,
            content={"error": "id 非法: 仅允许字母/数字/-/_, 禁止 .. / 绝对路径"},
        )
    proj_dir = Path(DATA_DIR) / house
    if not proj_dir.exists() or not proj_dir.is_dir():
        return JSONResponse(
            status_code=404,
            content={"error": f"项目 {house!r} 不存在"},
        )
    try:
        shutil.rmtree(proj_dir)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
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


@app.get("/api/projects/{house}/furniture")
def get_furniture(house: str):
    """读活家具文件 (B1 后为 {room_id,dx,dy} 相对键) 返回裸数组。"""
    path = _furniture_path(house)
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"furniture for house {house!r} not found"},
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/projects/{house}/save-furniture")
def save_furniture(house: str, furniture: list = Body(...)):
    """家具数组落盘 (沿用错误边界风格)。

    写盘格式与 B1 迁移落盘完全一致 (utf-8, ensure_ascii=False, indent=1, 无末换行),
    使「GET -> 原样 POST」回存的文件字节 / md5 不变。"""
    if not isinstance(furniture, list):
        return JSONResponse(
            status_code=400,
            content={"error": "furniture body must be a JSON array"},
        )
    path = _furniture_path(house)
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(furniture, fh, ensure_ascii=False, indent=1)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {"ok": True}


# render 同为同步 CPU 纯函数: 用 def 让 FastAPI 派发到线程池, 不阻塞事件循环。
@app.get("/api/projects/{house}/render")
def render_house(house: str, mode: str = "plan2d"):
    if mode not in _RENDER_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"mode must be one of {sorted(_RENDER_MODES)}, got {mode!r}"},
        )
    gpath = _geom_path(house)
    fpath = _furniture_path(house)
    if not gpath.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"geometry for house {house!r} not found"},
        )
    if not fpath.exists():
        return JSONResponse(
            status_code=404,
            content={"error": f"furniture for house {house!r} not found"},
        )
    try:
        G = geometry.load(str(gpath))
        geo = geometry.derive(G)
        with fpath.open("r", encoding="utf-8") as fh:
            furniture = json.load(fh)
        if mode == "plan2d":
            svg = axon.render_plan_2d(G, geo, furniture)          # out_path 省略 -> 仅返回字符串
            body = svg.encode("utf-8-sig")                        # 与 build.py 落盘一致 (带 BOM)
        else:
            geom = axon.geom_bundle(G, geo)
            svg = axon.render(geom, furniture, mode=mode)         # out_path 省略 -> 仅返回字符串
            body = svg.encode("utf-8")                            # 与 build.py 落盘一致 (无 BOM)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return Response(content=body, media_type="image/svg+xml")


# derive 是 GIL 下同步 CPU 纯函数: 用 def(非 async def) 让 FastAPI 自动丢线程池,
# 避免阻塞事件循环 (对抗 #14)。FastAPI 在 async 层解析 body, 再把本函数派发到线程池。
@app.post("/api/derive")
def derive(G: dict = Body(...)):
    try:
        res = geometry.derive(G)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
    # 与 serve.py /derive 字段对齐 (parity 基准)
    return _derive_payload(res)


def _derive_payload(res: dict) -> dict:
    """derive 结果 -> 统一裸对象 (serve.py /derive parity 基准)。"""
    return {
        "walls": res.get("walls", []),
        "doors": res.get("doors", []),
        "windows": res.get("windows", []),
        "dims": res.get("dims", {}),
        "conflicts": res.get("conflicts", []),
        "warns": res.get("warns", []),
        "_walls_raw": res.get("_walls_raw", []),
    }


# save-geometry 与 /derive 二分 (§⑨): /derive 为实时内存预览, save-geometry 走
# geometry.validate 校验; 有 ERROR -> 400 不落盘; 否则写活几何文件 + 返回派生结果。
# 不跑 build.py: React 编辑器实时渲 SVG, 不依赖磁盘 PNG/SVG 重出。
@app.post("/api/projects/{house}/save-geometry")
def save_geometry(house: str, G: dict = Body(...)):
    try:
        issues = geometry.validate(G)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})

    if GEOM_READONLY:
        # 只读护栏: 不落盘, 返回 403 (冒烟/测试会话防污染活红线几何文件)。
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: save-geometry disabled"},
        )

    errors = [msg for level, msg in issues if level == "ERROR"]
    warns = [msg for level, msg in issues if level == "WARN"]

    if errors:
        # 校验未过: 不写盘, 返回 400 + errors/warns (沿用现有错误边界风格)。
        return JSONResponse(
            status_code=400,
            content={"ok": False, "errors": errors, "warns": warns},
        )

    path = _geom_path(house)
    try:
        # 落盘活几何文件 (utf-8, 与 geometry.load 读侧一致)。
        with path.open("w", encoding="utf-8") as fh:
            json.dump(G, fh, ensure_ascii=False, indent=2)
        derived = geometry.derive(G)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return {"ok": True, "warns": warns, "derived": _derive_payload(derived)}
