# -*- coding: utf-8 -*-
"""阅天府软装 — 最小 FastAPI 后端 (Phase 0 walking skeleton)。

引擎接入: import floorplan_core (已 pip install -e packages/floorplan_core), 单一真源。
活编辑数据目录由 DATA_DIR(env) 指定, 默认基于 __file__ 相对推导到 data/projects/。
布局: {DATA_DIR}/{house}/geometry.json + {DATA_DIR}/{house}/furniture.json。
活数据已自引擎/红线目录 (轴测图POC) 迁出, 杜绝「测试期 save-geometry 误写红线参照」污染。
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import Body, FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from floorplan_core import axon, brief_prompt, catalog, geometry, prompt_gen  # 引擎库 (单一真源)

from starlette.concurrency import run_in_threadpool

from aigc.artifacts import ArtifactStore  # AI 子系统 (Phase 1 基础设施)
from aigc.budget import BudgetGuard
from aigc.config import get_settings
from aigc import acceptance, imaging, perspective
from aigc.modes import AXON_PHOTOREAL, REAL_PHOTO, RENDER_MODES
from aigc.errors import AIError, BudgetExceeded, ProviderError
from aigc.jobs import JobManager
from aigc.providers import MAX_EDIT_IMAGES, get_fal_provider, get_provider
from aigc.raster import pick_edit_size, pick_edit_size_for_svg, svg_to_png, svg_to_png_canvas
from aigc.records import RenderLog
import baselines as baseline_store
import furnish as furnish_service
import schemes as scheme_store

# 活编辑数据目录: 默认 = <repo>/data/projects (apps/api/main.py 上溯两级到 repo 根)。
# 注意: os.environ.get 的默认实参会被 **无条件求值**, 故默认路径推导须容错 ——
# 容器内 main.py 位于 /app (无 parents[2]) 时回退到同级 data/projects, 避免 IndexError 崩溃;
# 生产/容器恒设 DATA_DIR=/data/projects, 该回退仅为"未设 env 时"的防御 (宿主层级足够, 行为不变)。
def _default_data_dir() -> str:
    here = Path(__file__).resolve()
    try:
        return str(here.parents[2] / "data" / "projects")
    except IndexError:
        return str(here.parent / "data" / "projects")


DATA_DIR = os.environ.get("DATA_DIR", _default_data_dir())

HOUSE = os.environ.get("HOUSE", "D")
APP_VERSION = os.environ.get("APP_VERSION", "dev")

# 红线护栏: GEOM_READONLY 置真时 /save-geometry 拒写 (返回 403), 杜绝冒烟/测试会话
# 把 save-geometry 落盘污染活数据。活数据已迁出红线目录 (data/projects), 此护栏为双保险。
# 默认关 → 生产几何模式行为不变 (不破坏几何模式)。
GEOM_READONLY = os.environ.get("GEOM_READONLY", "").lower() in ("1", "true", "yes")

app = FastAPI(title="阅天府软装 API", version="0.0.1")


# 编辑器实时读写: 所有响应禁用缓存, 否则浏览器/Next 重载读到旧 geometry/furniture/render
# → 用户保存后刷新看似"未持久化"(实际磁盘已写). 等价于旧 serve.py 的 Cache-Control: no-store.
@app.middleware("http")
async def _no_store(request, call_next):
    resp = await call_next(request)
    # 编辑器实时数据禁缓存; 但 /api/artifacts 与 /api/uploads 是 uuid 不可变文件,
    # 由各自端点设置可缓存头, 此处不覆盖 (否则白白丢缓存)。
    path = request.url.path
    if not (path.startswith("/api/artifacts") or path.startswith("/api/uploads")):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


# --------------------------------------------------------------------------- #
#  AI 子系统单例 (Phase 1): 配置 / 预算护栏 / 异步任务 / 产物·上传存储。
#  凭据缺失时 _settings.ai_enabled=False, AI 端点 503; 主服务 (几何/渲染) 不受影响。
# --------------------------------------------------------------------------- #
_settings = get_settings()
_budget = BudgetGuard(_settings)
_jobs = JobManager()
_artifacts = ArtifactStore(_settings.artifacts_dir)
_uploads = ArtifactStore(_settings.uploads_dir)
_renders = RenderLog(_settings.artifacts_dir)


# AI 异常 -> HTTP 状态码映射 (errors.py 契约): 预算 402 / provider 502 / 其它 AI 500。
# 生成端点 (Phase 2/4) 抛这些异常即被统一翻译, 无需各处手写。
@app.exception_handler(BudgetExceeded)
async def _on_budget_exceeded(_request, exc):
    return JSONResponse(status_code=402, content={"error": str(exc)})


@app.exception_handler(ProviderError)
async def _on_provider_error(_request, exc):
    return JSONResponse(status_code=502, content={"error": str(exc)})


@app.exception_handler(AIError)
async def _on_ai_error(_request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})


def _geom_path(house: str) -> Path:
    return Path(DATA_DIR) / house / "geometry.json"


def _furniture_path(house: str) -> Path:
    return Path(DATA_DIR) / house / "furniture.json"


def _atomic_write_json(path: Path, obj, *, indent: int) -> None:
    """原子落盘 JSON: 写同目录 *.tmp + flush+os.fsync + os.replace; 覆盖前留 .bak 单步回退。

    崩溃安全: 任意时刻 path 要么是旧完整版、要么是新完整版, 绝不出现被截断的半截文件
    (kill -9 / 异常中断后文件仍完整)。落盘字节与旧
    `open("w") + json.dump(obj, fh, ensure_ascii=False, indent=indent)` **逐字节一致**
    (往返 byte 不破): 同样 utf-8 / ensure_ascii=False / 指定 indent / 无末换行。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    # 1) 全量写临时文件并 flush+fsync, 确保数据真正落到磁盘 (而非仅在页缓存)。
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=indent)
        fh.flush()
        os.fsync(fh.fileno())
    # 2) 覆盖前留 .bak (单步回退): 先把旧版复制成 .bak, 原文件全程保持完整, 仅在第 3 步原子替换。
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        shutil.copyfile(path, bak)
    # 3) os.replace 原子替换 (同一文件系统内为原子 rename), 中断点落在替换前=旧版完整, 替换后=新版完整。
    os.replace(tmp, path)
    # 4) fsync 目录项, 让 rename 的元数据也持久化 (best-effort, 失败不影响数据完整性)。
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


# 项目 id 安全校验: 仅字母/数字/-/_; 拒 ..、/、绝对路径 (防路径穿越)。
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_project_id(pid: str) -> bool:
    """项目 id 路径安全: 仅 [A-Za-z0-9_-], 非空, 杜绝 ../、绝对路径、分隔符。"""
    return bool(pid) and bool(_PROJECT_ID_RE.match(pid))


def _scheme_error_response(exc: Exception) -> JSONResponse:
    """Map scheme storage exceptions to the API's existing JSON error style."""
    if isinstance(exc, scheme_store.SchemeValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if isinstance(exc, scheme_store.SchemeNotFound):
        return JSONResponse(status_code=404, content={"error": str(exc)})
    if isinstance(exc, scheme_store.SchemeConflict):
        return JSONResponse(status_code=409, content={"error": str(exc)})
    if isinstance(exc, scheme_store.SchemeError):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": str(exc)})


def _baseline_error_response(exc: Exception) -> JSONResponse:
    """Map baseline storage exceptions to the API's existing JSON error style."""
    if isinstance(exc, baseline_store.BaselineValidationError):
        detail = exc.args[0] if exc.args else str(exc)
        if isinstance(detail, dict):
            return JSONResponse(status_code=400, content={"error": "validation failed", **detail})
        return JSONResponse(status_code=400, content={"error": str(exc)})
    if isinstance(exc, baseline_store.BaselineNotFound):
        return JSONResponse(status_code=404, content={"error": str(exc)})
    if isinstance(exc, baseline_store.BaselineConflict):
        return JSONResponse(status_code=409, content={"error": str(exc)})
    if isinstance(exc, baseline_store.BaselineError):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": str(exc)})


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
def health():
    """真实探活: ① DATA_DIR 存在且可写 (写删临时文件) ② 引擎 floorplan_core 可导入。

    任一失败返 503 (供 docker healthcheck / nginx 探活判 DOWN); 正常返
    {"ok": True, "readonly": <GEOM_READONLY>}, readonly 暴露只读护栏状态供监控告警。
    """
    # ① DATA_DIR 可写探针: 写一个临时文件再删, 真正验证 uid 对 bind 卷有写权限 (而非仅存在)。
    data_dir = Path(DATA_DIR)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / f".health-{os.getpid()}.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception as exc:  # noqa: BLE001 — 探活边界: 写不进=不健康, 显式 503
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "readonly": GEOM_READONLY,
                "error": f"DATA_DIR not writable: {exc}",
            },
        )
    # ② 引擎可导入探针: 渲染依赖 floorplan_core, 导入失败 = 整服务不可用。
    try:
        importlib.import_module("floorplan_core")
    except Exception as exc:  # noqa: BLE001 — 探活边界: 引擎缺失=不健康, 显式 503
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "readonly": GEOM_READONLY,
                "error": f"engine import failed: {exc}",
            },
        )
    # ③ 已迁移项目元数据可读性: 若 HOUSE 项目已存在 project.json，则当前版本必须可读。
    try:
        project_dir = Path(DATA_DIR) / HOUSE
        if (project_dir / "project.json").exists():
            project_meta = baseline_store.get_project(DATA_DIR, HOUSE)
            current_id = project_meta.get("current_baseline_version_id")
            if current_id:
                baseline_store.get_baseline(DATA_DIR, HOUSE, str(current_id))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "readonly": GEOM_READONLY,
                "error": f"project metadata unreadable: {exc}",
            },
        )
    return {"ok": True, "readonly": GEOM_READONLY, "version": APP_VERSION}


@app.get("/api/catalog")
def get_catalog():
    """家具目录单一真源 (P2 前后端同源): 前端家具库据此出类型清单 + 真实默认尺寸 + 分组。

    出参 {rev, types}: rev=CATALOG_REV (前端可据此判缓存失效); types=引擎目录逐条
    (t/en/shape/w/h|r/z?/color?/rooms/zh/category/tall?/directional?)。静态、无副作用。
    结构件 (partition/entry_door/rug) 不在目录, 前端本地补充。
    """
    return {"rev": catalog.CATALOG_REV, "types": catalog.to_public()}


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

    # mkdir(exist_ok=False) 是并发安全的存在性判定: 输给对手时返回 409,
    # 绝不 rmtree (那是对手刚建的目录 —— 审计确认过的并发数据丢失竞态)。
    try:
        proj_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return JSONResponse(status_code=409, content={"error": f"项目 {pid!r} 已存在"})
    try:
        # 原子写 (新建项目无旧版, 故无 .bak); 字节同旧 open(w)+json.dump(indent=2/1)。
        _atomic_write_json(_geom_path(pid), G, indent=2)
        _atomic_write_json(_furniture_path(pid), [], indent=1)
        baseline_store.initialize_new_project(DATA_DIR, pid, name=name, geometry_payload=G)
    except Exception as exc:  # noqa: BLE001 — 仅回滚自己刚创建的目录 (mkdir 成功才会进到这里)
        shutil.rmtree(proj_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(status_code=201, content=_project_summary(pid))


@app.delete("/api/projects/{house}")
def delete_project(house: str):
    """软删项目: 不 rmtree, 先 mv 到 {DATA_DIR}/.trash/{id}-{ts} (可恢复, 防误删/进程崩溃损毁)。

    id 安全校验防路径穿越; 不受 GEOM_READONLY 影响。.trash 内不含顶层 geometry.json,
    故不会被 list_projects 当成项目列出。回收站保留, 由 backup/清理脚本按 N 天淘汰。
    """
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
        trash = Path(DATA_DIR) / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        dest = trash / f"{house}-{ts}"
        shutil.move(str(proj_dir), str(dest))
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return {"ok": True, "trashed": dest.name}


@app.get("/api/projects/{house}")
def get_project(house: str):
    try:
        return baseline_store.get_project(DATA_DIR, house)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.get("/api/projects/{house}/baselines")
def list_project_baselines(house: str):
    try:
        return baseline_store.list_baselines(DATA_DIR, house)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines")
def create_project_baseline(house: str, payload: dict = Body(default_factory=dict)):
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        meta = baseline_store.create_baseline(DATA_DIR, house, payload)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)
    return JSONResponse(status_code=201, content=meta)


@app.get("/api/projects/{house}/baselines/{version}")
def get_project_baseline(house: str, version: str):
    try:
        return baseline_store.get_baseline(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.get("/api/projects/{house}/baselines/{version}/geometry")
def get_project_baseline_geometry(house: str, version: str):
    try:
        return baseline_store.read_baseline_geometry(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines/{version}/save-geometry")
def save_project_baseline_geometry(house: str, version: str, G: dict = Body(...)):
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        result = baseline_store.save_baseline_geometry(DATA_DIR, house, version, G)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)
    # 契约统一 (审计 P2): 校验失败 = 400 (与 legacy /save-geometry 一致), 不再 200+ok:false
    # 的分叉形状; body 仍带 ok/errors/warns 供前端展示。
    if isinstance(result, dict) and result.get("ok") is False:
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/projects/{house}/baselines/{version}/furniture")
def get_project_baseline_furniture(house: str, version: str):
    """基线标准布局家具 (Phase A: 家具下沉基线)。v1 未物化时回退根 furniture.json。"""
    try:
        return baseline_store.read_baseline_furniture(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines/{version}/save-furniture")
def save_project_baseline_furniture(
    house: str, version: str, furniture: list = Body(...)
):
    """保存基线家具 (仅草稿版本可写, 确认即只读)。沿用 baseline 写约定的 403 门禁。"""
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    # 逐件写边界护栏 (审计 P1-3, 与方案家具写端点一致): 坏件在写入口 400+定位, 不落盘 ——
    # 基线家具后续会被方案 seed 并进渲染, 无 t/room_id/坐标件会致第4/5步 KeyError→500。
    err = _furniture_items_error(furniture)
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    try:
        return baseline_store.save_baseline_furniture(DATA_DIR, house, version, furniture)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines/{version}/validate")
def validate_project_baseline(house: str, version: str):
    # validate 会写 validation.json 并可能触发首次结构迁移(落盘),属写路径:
    # 只读会话必须 403, 否则单点绕过 GEOM_READONLY 护栏污染活数据(与其余 baseline 写路由一致)。
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        return baseline_store.validate_baseline(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines/{version}/confirm")
def confirm_project_baseline(house: str, version: str):
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        return baseline_store.confirm_baseline(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


# ---- 第6步: 空房照片 (绑定户型版本, 不绑定方案 — 规格 §8.3) ---- #


@app.get("/api/projects/{house}/baselines/{version}/photos")
def list_baseline_photos(house: str, version: str):
    try:
        return baseline_store.list_photos(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.post("/api/projects/{house}/baselines/{version}/photos")
async def upload_baseline_photo(
    house: str,
    version: str,
    file: UploadFile = File(...),
    room_id: Optional[str] = Form(None),
    direction: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    purpose: Optional[str] = Form(None),
):
    """上传空房实拍照并登记到户型版本。文件复用 uploads 自托管 (kind=empty)。
    purpose (P2 材质C): 缺省=空房底图; wall_material=墙面材质参考图 (由 walls.photo_id 引用)。"""
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    # 标注字段先于落盘校验 (审查建议): 非法 direction/purpose 不再留下已写盘的孤儿文件。
    if direction is not None and direction not in baseline_store.PHOTO_DIRECTIONS:
        return JSONResponse(
            status_code=400,
            content={"error": f"direction 必须为 {sorted(baseline_store.PHOTO_DIRECTIONS)} 之一"},
        )
    if purpose is not None and purpose not in baseline_store.PHOTO_PURPOSES:
        return JSONResponse(
            status_code=400,
            content={"error": f"purpose 必须为 {sorted(baseline_store.PHOTO_PURPOSES)} 之一"},
        )
    ext = _UPLOAD_EXT.get((file.content_type or "").lower())
    if ext is None:
        return JSONResponse(
            status_code=415, content={"error": f"不支持的图片类型: {file.content_type}"}
        )
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "文件过大 (>15MB)"})
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not data:
        return JSONResponse(status_code=400, content={"error": "空文件"})
    if len(data) > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "文件过大 (>15MB)"})
    # 归一化 (审计 P0-2): 验真身 / 物化 EXIF 方向 / 剥 GPS / 压边 -> 稳定 JPEG + 元数据。
    try:
        normalized, meta = await run_in_threadpool(imaging.normalize_photo, data)
    except AIError as exc:
        return JSONResponse(status_code=415, content={"error": str(exc)})
    try:
        rel = await run_in_threadpool(
            _uploads.save, normalized, project_id=house, kind="empty", ext="jpg"
        )
        thumb_url = None
        try:
            thumb_rel = await run_in_threadpool(
                _uploads.save,
                imaging.make_thumb(normalized),
                project_id=house,
                kind="empty-thumb",
                ext="webp",
            )
            thumb_url = f"/api/uploads/{thumb_rel}"
        except Exception:  # noqa: BLE001 - 缩略图失败不阻断上传。
            pass
        entry = {
            "id": uuid.uuid4().hex,
            "url": f"/api/uploads/{rel}",
            "thumb_url": thumb_url,
            "room_id": room_id,
            "direction": direction,
            "note": note,
            "purpose": purpose,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "width": meta["width"],
            "height": meta["height"],
            "mime": meta["mime"],
            "sha256": meta["sha256"],
            # B5: 服务器派生的照片质量评分 (只读, 非用户可 patch); 前端展示可用性徽标。
            "quality": meta.get("quality"),
        }
        entry = await run_in_threadpool(
            baseline_store.add_photo, DATA_DIR, house, version, entry
        )
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)
    return JSONResponse(status_code=201, content=entry)


@app.patch("/api/projects/{house}/baselines/{version}/photos/{photo_id}")
def patch_baseline_photo(house: str, version: str, photo_id: str, payload: dict = Body(...)):
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        return baseline_store.update_photo(DATA_DIR, house, version, photo_id, payload or {})
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


def _validate_calibration_payload(p: dict) -> Optional[str]:
    """透视标定入参校验 (P2b): 2 组墙线各 >=2 条 [[x,y],[x,y]] + >=2 锚点 {world,px} + img_wh。"""
    if not isinstance(p, dict):
        return "标定数据必须为对象"
    for key in ("x_lines", "y_lines"):
        v = p.get(key)
        if not isinstance(v, list) or len(v) < 2:
            return f"{key} 需 >=2 条平行墙线"
        for ln in v:
            if not (isinstance(ln, list) and len(ln) == 2
                    and all(isinstance(pt, list) and len(pt) == 2 for pt in ln)):
                return f"{key} 每条线须为 [[x,y],[x,y]]"
    anchors = p.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 2:
        return "anchors 需 >=2 个 (在照片上点 2 个墙角)"
    for a in anchors:
        if not (isinstance(a, dict) and isinstance(a.get("world"), list) and len(a["world"]) == 3
                and isinstance(a.get("px"), list) and len(a["px"]) == 2):
            return "每个 anchor 须为 {world:[x,y,z], px:[u,v]}"
    wh = p.get("img_wh")
    if not (isinstance(wh, list) and len(wh) == 2
            and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in wh)):
        return "img_wh 须为 [W,H]"
    return None


def _calibration_camera(p: dict) -> "perspective.Camera":
    def _lines(key):
        return [((ln[0][0], ln[0][1]), (ln[1][0], ln[1][1])) for ln in p[key]]

    anchors = [
        ((a["world"][0], a["world"][1], a["world"][2]), (a["px"][0], a["px"][1]))
        for a in p["anchors"]
    ]
    return perspective.calibrate(
        _lines("x_lines"), _lines("y_lines"), anchors,
        img_wh=(int(p["img_wh"][0]), int(p["img_wh"][1])),
    )


@app.post("/api/projects/{house}/baselines/{version}/photos/{photo_id}/calibration")
def set_photo_calibration_ep(
    house: str, version: str, photo_id: str, payload: dict = Body(...)
):
    """P2b 透视标定: 用户拖 2 组正交墙线 + 点 2 墙角 -> 反解相机 -> 存照片记录 (几何锁定出图用)。"""
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    err = _validate_calibration_payload(payload or {})
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    try:
        cam = _calibration_camera(payload)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return JSONResponse(status_code=400, content={"error": f"标定失败: {exc}"})
    calibration = {
        "x_lines": payload["x_lines"],
        "y_lines": payload["y_lines"],
        "anchors": payload["anchors"],
        "img_wh": payload["img_wh"],
        "camera": cam.to_dict(),
    }
    try:
        return baseline_store.set_photo_calibration(
            DATA_DIR, house, version, photo_id, calibration
        )
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.delete("/api/projects/{house}/baselines/{version}/photos/{photo_id}")
def delete_baseline_photo(house: str, version: str, photo_id: str):
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        return baseline_store.delete_photo(DATA_DIR, house, version, photo_id)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


@app.delete("/api/projects/{house}/baselines/{version}")
def delete_project_baseline(house: str, version: str):
    """软删户型版本 (级联绑定方案入回收站)。只能删草稿/历史版本; 当前已确认版本与
    最后一个版本受后端 409 保护。沿用 baseline 写约定的 GEOM_READONLY 403 门禁。"""
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    try:
        return baseline_store.delete_baseline(DATA_DIR, house, version)
    except Exception as exc:  # noqa: BLE001
        return _baseline_error_response(exc)


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
    try:
        return scheme_store.read_furniture(DATA_DIR, house, "default")
    except Exception as exc:  # noqa: BLE001 — 保持边界处 JSON 错误风格
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/save-furniture")
def save_furniture(house: str, furniture: list = Body(...)):
    """家具数组落盘 (沿用错误边界风格)。

    写盘格式与 B1 迁移落盘完全一致 (utf-8, ensure_ascii=False, indent=1, 无末换行),
    使「GET -> 原样 POST」回存的文件字节 / md5 不变。"""
    err = _furniture_items_error(furniture)
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    try:
        scheme_store.write_furniture(DATA_DIR, house, "default", furniture)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return _scheme_error_response(exc)
    return {"ok": True}


@app.get("/api/projects/{house}/schemes")
def list_project_schemes(
    house: str,
    baseline_version_id: Optional[str] = None,
    include_archived: bool = False,
):
    try:
        schemes = scheme_store.list_schemes(
            DATA_DIR,
            house,
            baseline_version_id=baseline_version_id,
            include_archived=include_archived,
        )
        # 多方案上线前的默认效果图历史保存在 ARTIFACTS_DIR/{house}/renders.json。
        # 默认方案迁移后仍合并展示旧历史，避免升级时历史记录从 UI 消失。
        default_renders = _list_default_renders(house)
        for scheme in schemes:
            if scheme.get("id") == "default":
                scheme["renders"] = len(default_renders)
                break
        return schemes
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes")
def create_project_scheme(house: str, payload: dict = Body(...)):
    err = _furniture_items_error((payload or {}).get("furniture") or [])
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    try:
        meta = scheme_store.create_scheme(DATA_DIR, house, payload)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return JSONResponse(status_code=201, content=meta)


@app.get("/api/projects/{house}/schemes/{scheme_id}")
def get_project_scheme(house: str, scheme_id: str):
    try:
        return scheme_store.get_scheme(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.patch("/api/projects/{house}/schemes/{scheme_id}")
def patch_project_scheme(house: str, scheme_id: str, payload: dict = Body(...)):
    try:
        return scheme_store.patch_scheme(DATA_DIR, house, scheme_id, payload)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


# Phase D (D-2): /confirm 与 /adjust 端点已移除 —— 方案不再有确认锁; 需要副本走 /duplicate。


@app.post("/api/projects/{house}/schemes/{scheme_id}/restore")
def restore_project_scheme(house: str, scheme_id: str):
    """恢复已归档方案 (Phase D / D-5): archived -> draft。归档=可逆暂存。"""
    try:
        return scheme_store.restore_scheme(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/archive")
def archive_project_scheme(house: str, scheme_id: str):
    try:
        return scheme_store.archive_scheme(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/set-preferred")
def set_preferred_project_scheme(house: str, scheme_id: str):
    try:
        return scheme_store.set_preferred(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/migrate")
def migrate_project_scheme(house: str, scheme_id: str, payload: dict = Body(...)):
    try:
        meta = scheme_store.migrate_scheme(DATA_DIR, house, scheme_id, payload)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return JSONResponse(status_code=201, content=meta)


@app.delete("/api/projects/{house}/schemes/{scheme_id}")
def delete_project_scheme(house: str, scheme_id: str):
    try:
        return scheme_store.delete_scheme(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/duplicate")
def duplicate_project_scheme(house: str, scheme_id: str, payload: dict = Body(...)):
    try:
        meta = scheme_store.duplicate_scheme(DATA_DIR, house, scheme_id, payload)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return JSONResponse(status_code=201, content=meta)


@app.get("/api/projects/{house}/schemes/{scheme_id}/furniture")
def get_scheme_furniture(house: str, scheme_id: str):
    try:
        return scheme_store.read_furniture(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/save-furniture")
def save_scheme_furniture(house: str, scheme_id: str, furniture: list = Body(...)):
    err = _furniture_items_error(furniture)
    if err:
        return JSONResponse(status_code=400, content={"error": err})
    try:
        scheme_store.write_furniture(DATA_DIR, house, scheme_id, furniture)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return {"ok": True}


# render 同为同步 CPU 纯函数: 用 def 让 FastAPI 派发到线程池, 不阻塞事件循环。
def _render_house_response(
    house: str, mode: str, scheme_id: str, fmt: str = "svg"
) -> Response | JSONResponse:
    if mode not in _RENDER_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"mode must be one of {sorted(_RENDER_MODES)}, got {mode!r}"},
        )
    if fmt not in ("svg", "png"):
        return JSONResponse(status_code=400, content={"error": "format must be svg|png"})
    try:
        G, geo, furniture, _scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        if mode == "plan2d":
            svg = axon.render_plan_2d(G, geo, furniture)          # out_path 省略 -> 仅返回字符串
            body = svg.encode("utf-8-sig")                        # 与 build.py 落盘一致 (带 BOM)
        else:
            geom = axon.geom_bundle(G, geo)
            svg = axon.render(geom, scene["axon_furniture"], mode=mode)  # 轴侧使用 scene 安全坐标
            body = svg.encode("utf-8")                            # 与 build.py 落盘一致 (无 BOM)
        if fmt == "png":
            # 交付物栅格 (审计 P1-7): PNG 无脚本执行面, 且外部看图器不会丢 SVG 滤镜。
            body = svg_to_png(svg, width=1536)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})
    if fmt == "png":
        return Response(content=body, media_type="image/png")
    # SVG 含用户文本: 已在引擎侧转义; 再加 nosniff + CSP sandbox, 顶层打开也无脚本执行面。
    return Response(
        content=body,
        media_type="image/svg+xml",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


def _prompt_items_from_axon(axon_items: list, G: dict) -> list:
    """把轴测归一化后的家具转回 room-relative 条目供提示词消费 (审计 P1-8)。

    方位短语必须描述「底图里画的位置」: 归一化 (贴边/避墙) 可位移家具, 若仍用原始
    dx/dy, prompt 会与底图矛盾。_dx/_dy|_dcx/_dcy 由 build_scene 回填。"""
    rects = {r.get("id"): r.get("rect") for r in G.get("rooms", [])}
    out: list[dict] = []
    for it in axon_items:
        rid = it.get("_room_id")
        if rid is None or rid not in rects:
            out.append(dict(it))
            continue
        base: dict = {"t": it.get("t"), "room_id": rid}
        if "_dx" in it and "_dy" in it:
            base.update(dx=it["_dx"], dy=it["_dy"], w=it.get("w"), h=it.get("h"))
        elif "_dcx" in it and "_dcy" in it:
            base.update(dcx=it["_dcx"], dcy=it["_dcy"], r=it.get("r"))
        else:
            out.append(dict(it))
            continue
        out.append(base)
    return out


def _furniture_items_error(items) -> str | None:
    """家具写边界校验 (审计 P1-3): 坏件在写入口 400+定位, 不再延迟到第4/5步 KeyError->500。

    绝对坐标旧格式 (无 room_id) 同步收口 (生产 0 件在用, 审计确认)。"""
    if not isinstance(items, list):
        return "furniture 必须为数组"

    def _num(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            return f"furniture[{i}] 必须是对象"
        t = it.get("t")
        if not isinstance(t, str) or not t.strip():
            return f"furniture[{i}] 缺少家具类型 t"
        if it.get("room_id") is None:
            return f"furniture[{i}] ({t}) 缺少 room_id (绝对坐标旧格式已停用)"
        rel_ok = (_num(it.get("dx")) and _num(it.get("dy"))) or (
            _num(it.get("dcx")) and _num(it.get("dcy"))
        )
        if not rel_ok:
            return f"furniture[{i}] ({t}) 缺少数值 dx/dy 或 dcx/dcy"
        has_size = _num(it.get("r")) or (_num(it.get("w")) and _num(it.get("h")))
        if not has_size and catalog.appearance(t) is None:
            return f"furniture[{i}] ({t}) 缺少尺寸 (w/h 或 r) 且家具目录无该类型"
    return None


def _load_scheme_scene(house: str, scheme_id: str) -> tuple[dict, dict, list, dict, dict]:
    """Load scheme-bound baseline geometry/furniture and build canonical scene."""
    scheme_meta = scheme_store.get_scheme(DATA_DIR, house, scheme_id)
    baseline_id = str(scheme_meta.get("baseline_version_id") or "v1")
    G = baseline_store.read_baseline_geometry(DATA_DIR, house, baseline_id)
    geo = geometry.derive(G)
    furniture = scheme_store.read_furniture(DATA_DIR, house, scheme_id)
    scene = axon.build_scene(
        G,
        geo,
        furniture,
        project_id=house,
        baseline_version_id=baseline_id,
        scheme_id=scheme_id,
    )
    return G, geo, furniture, scheme_meta, scene


@app.get("/api/projects/{house}/render")
def render_house(house: str, mode: str = "plan2d", format: str = "svg"):
    return _render_house_response(house, mode, "default", format)


@app.get("/api/projects/{house}/schemes/{scheme_id}/render")
def render_scheme_house(
    house: str, scheme_id: str, mode: str = "plan2d", format: str = "svg"
):
    return _render_house_response(house, mode, scheme_id, format)


@app.get("/api/projects/{house}/schemes/{scheme_id}/axon-view")
def axon_view_preview(house: str, scheme_id: str, room_id: str = "", view: str = "v0"):
    """拍摄视角对齐预览 (实拍对齐): 按 room 切片 + 按 view 旋转的软装轴测 SVG, 供上传照片时
    "所见即所得"挑视角 (哪个缩略图像你的照片就选哪个)。纯读、无副作用、不生成 AI 图。"""
    try:
        G, geo, _furniture, _scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        geom = axon.geom_bundle(G, geo)
        axon_furniture = scene["axon_furniture"]
        if room_id:
            try:
                member_ids = axon.merge_group_ids(G, room_id)
                geom = axon.slice_geom_for_room(geom, room_id)
                axon_furniture = [
                    it for it in axon_furniture if it.get("_room_id") in member_ids
                ]
            except ValueError:
                pass  # 房间已删/改名 -> 回退整宅
        svg = axon.render(
            geom, axon_furniture, mode="photo", quarter_turns=_view_quarter_turns(view)
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return Response(
        content=svg.encode("utf-8"),
        media_type="image/svg+xml",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


def _slice_axon_for_room(house: str, scheme_id: str, room_id: str, quarter_turns: int) -> str:
    """渲染某房某视角的软装轴测 SVG (axon-view / suggest-view 共用)。"""
    G, geo, _furniture, _meta, scene = _load_scheme_scene(house, scheme_id)
    geom = axon.geom_bundle(G, geo)
    axon_furniture = scene["axon_furniture"]
    if room_id:
        try:
            member_ids = axon.merge_group_ids(G, room_id)
            geom = axon.slice_geom_for_room(geom, room_id)
            axon_furniture = [it for it in axon_furniture if it.get("_room_id") in member_ids]
        except ValueError:
            pass
    return axon.render(geom, axon_furniture, mode="photo", quarter_turns=quarter_turns)


def _window_side_for_room(house: str, scheme_id: str, room_id: str, k: int) -> str:
    """某房某视角下, 主窗(最宽的窗)在画面哪一侧 -> 左/右/正对/无窗。直接解析真实渲染的
    SVG 里蓝色窗多边形的 x 中心 vs 画布中心, 故与投影/旋转天然一致 (无需手推方位)。"""
    svg = _slice_axon_for_room(house, scheme_id, room_id, k)
    m = re.search(r'viewBox="([\d.\- ]+)"', svg)
    if not m:
        return "无窗"
    vx, _vy, vw, _vh = (float(v) for v in m.group(1).split())
    cx = vx + vw / 2
    wins = re.findall(r'<polygon points="([^"]+)" fill="#bfe0f0', svg)
    best_c, best_w = None, -1.0
    for pts in wins:
        xs = [float(p.split(",")[0]) for p in pts.split() if "," in p]
        if not xs:
            continue
        span = max(xs) - min(xs)
        if span > best_w:
            best_w, best_c = span, sum(xs) / len(xs)
    if best_c is None:
        return "无窗"
    off = (best_c - cx) / vw
    return "左" if off < -0.1 else ("右" if off > 0.1 else "正对")


@app.get("/api/projects/{house}/schemes/{scheme_id}/view-hints")
def view_hints(house: str, scheme_id: str, room_id: str = ""):
    """4 个视角各自的主窗方位 (给选择器标注"窗在左/右", 让用户一眼对上照片)。纯读、无 AI。"""
    if not room_id:
        return {"hints": {}}
    try:
        return {"hints": {f"v{k}": _window_side_for_room(house, scheme_id, room_id, k) for k in range(4)}}
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return {"hints": {}}


@app.post("/api/projects/{house}/schemes/{scheme_id}/suggest-view")
def suggest_view(house: str, scheme_id: str, payload: dict = Body(...)):
    """自动判定拍摄视角 (问题1 解法, 尽力而为): 把空房照 + 4 张旋转轴测缩略图交给 gpt-5.5
    视觉, 问哪个机位最像照片, 返回 {suggested: "vN"|null}。AI 未启用 / 失败 -> null, 不阻断
    (前端仍可手动选)。纯建议、不落盘、不生成 AI 图。"""
    photo_id = (payload or {}).get("photo_id")
    if not photo_id:
        return JSONResponse(status_code=400, content={"error": "缺 photo_id"})
    if not _settings.api_key or not _settings.base_url:
        return {"suggested": None, "reason": "ai_disabled"}
    try:
        # 照片按户型版本分目录存; 用方案绑定的 baseline 版本, 不硬编码 v1 (进阶户型 v2..v6
        # 会读错版本 -> 404 -> 视角推荐永久失效, 削弱实拍落位)。审计 C / 与 render-real 一致。
        scheme_meta = scheme_store.get_scheme(DATA_DIR, house, scheme_id)
        baseline_id = str(scheme_meta.get("baseline_version_id") or "v1")
        photos = baseline_store.list_photos(DATA_DIR, house, baseline_id)
        photo = next((p for p in photos if p.get("id") == str(photo_id)), None)
        if not photo:
            return JSONResponse(status_code=404, content={"error": "照片不存在"})
        room_id = str(photo.get("room_id") or "")
        if not room_id:
            return {"suggested": None, "reason": "no_room"}
        url = str(photo.get("url") or "")
        rel = url[len("/api/uploads/"):] if url.startswith("/api/uploads/") else ""
        target = _uploads.resolve(rel) if rel else None
        if target is None:
            return {"suggested": None, "reason": "no_photo_file"}
        photo_b64 = base64.b64encode(target.read_bytes()).decode()
        # 4 视角轴测 -> 小 PNG (512, 省 token)
        views = []
        for k in range(4):
            svg = _slice_axon_for_room(house, scheme_id, room_id, k)
            png = svg_to_png(svg, width=512)
            views.append(base64.b64encode(png).decode())
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return {"suggested": None, "reason": f"prep_failed: {exc}"}

    content = [
        {"type": "text", "text": (
            "第一张=空房实拍照; 后面 v0..v3=同一房间从不同角落看的等距轴测缩略图。三步判断: "
            "(1)照片里大窗/主采光面在画面哪侧(左/右/正对/无窗)、能看到哪几面墙; "
            "(2)对每张轴测同样判断窗面与可见墙方位; "
            "(3)选窗面方位+可见墙与照片最一致的一张。返回 JSON: {\"reason\":\"简述\",\"view\":\"vN\"}, N 取 0..3。"
        )},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"}},
    ]
    for i, v in enumerate(views):
        content.append({"type": "text", "text": f"v{i}:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{v}"}})
    try:
        provider = get_provider(_settings)
        out = provider.chat_json([{"role": "user", "content": content}])
        v = str(out.get("view") or "").strip().lower()
        return {"suggested": v if v in _VIEW_TURNS else None}
    except Exception as exc:  # noqa: BLE001 — 视觉判定失败不阻断, 前端手动选
        return {"suggested": None, "reason": f"vision_failed: {exc}"}


@app.get("/api/projects/{house}/schemes/{scheme_id}/scene")
def get_scheme_scene(house: str, scheme_id: str):
    try:
        _G, _geo, _furniture, _scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        return scene
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/projects/{house}/scene")
def get_default_scene(house: str):
    return get_scheme_scene(house, "default")


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

    # Baseline-aware projects must not use the legacy root geometry write path at all:
    # 草稿走 /baselines/{version}/save-geometry, 已确认/历史版本只读锁定, 根 geometry 仅由
    # confirm 镜像。历史遗留 bug: 旧实现只在 current.status=='confirmed' 时拒写,
    # 若 confirm 崩溃使 current 指向 superseded 版本, 门禁会失效致根几何被旧接口覆盖。
    # 现改为「已启用版本管理即一律拒绝旧接口直写」, 与 confirm 崩溃安全排序双重兜底。
    project_meta_path = Path(DATA_DIR) / house / "project.json"
    if project_meta_path.exists():
        try:
            project_meta = baseline_store.get_project(DATA_DIR, house)
            current_id = project_meta.get("current_baseline_version_id")
            if not current_id:
                return JSONResponse(
                    status_code=409,
                    content={
                        "ok": False,
                        "error": "当前没有已确认户型，请通过户型草稿版本保存",
                    },
                )
            return JSONResponse(
                status_code=409,
                content={
                    "ok": False,
                    "error": "户型已启用版本管理，不能通过旧接口覆盖根几何，请在户型草稿版本中保存",
                },
            )
        except Exception as exc:  # noqa: BLE001
            return _baseline_error_response(exc)

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
        # 原子写活几何文件 (覆盖前留 .bak; utf-8, 与 geometry.load 读侧一致); 字节同旧 indent=2。
        _atomic_write_json(path, G, indent=2)
        derived = geometry.derive(G)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return {"ok": True, "warns": warns, "derived": _derive_payload(derived)}


# --------------------------------------------------------------------------- #
#  AI 子系统端点 (Phase 1 基础设施)
#  生成端点 (render-ai / stage-real) 属 Phase 2/4; 此处仅状态/产物/上传/任务轮询底座。
# --------------------------------------------------------------------------- #
@app.get("/api/ai/status")
def ai_status():
    """AI 是否可用 + 模型 + 预算余量 (前端据此显隐/禁用 AI 功能, 凭据缺失即灰显)。"""
    return {
        "enabled": _settings.ai_enabled,
        "provider": _settings.provider,
        "model": _settings.model,
        "budget": _budget.status(),
        # 几何锁定编辑后端: 前端"换后端重试"按钮据此判断可切目标 (fal 缺 key 即不可用)。
        # 归一化与路由判定一致 (env 非 "fal" 一律按 relay 执行), 防 env 配错时显示与执行不符。
        "geometry_edit_backend": "fal" if _settings.geometry_edit_backend == "fal" else "relay",
        "fal_enabled": _settings.fal_enabled,
    }


@app.get("/api/ai/jobs/{job_id}")
def ai_job(job_id: str):
    """轮询异步生成任务状态 (queued/running/done/error)。traceback 不外泄, 仅 error 摘要。"""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": f"job {job_id!r} not found"})
    return {k: job.get(k) for k in ("id", "status", "result", "error", "meta", "created", "updated")}


def _ai_scheme_id(idx: int) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    return f"scheme_ai_{ts}_{idx:02d}_{os.urandom(2).hex()}"


@app.post("/api/projects/{house}/furnish")
def furnish_house(house: str, payload: Optional[dict] = Body(default=None)):
    """第2步: AI 根据空户型生成 1..N 个候选 FurnitureScheme。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    if not _settings.ai_enabled:
        return JSONResponse(
            status_code=503, content={"error": "AI 未配置 (缺 OPENAI_API_KEY / OPENAI_BASE_URL)"}
        )
    body = payload or {}
    style_prompt = body.get("style_prompt")
    if not isinstance(style_prompt, str) or not style_prompt.strip():
        return JSONResponse(status_code=400, content={"error": "style_prompt 必须为非空字符串"})
    try:
        count = int(body.get("count", 1))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "count 必须为整数"})
    if count < 1 or count > 4:
        return JSONResponse(status_code=400, content={"error": "count 必须在 1..4 之间"})
    base_scheme_id = body.get("base_scheme_id") or "default"
    try:
        scheme_store.assert_can_create_from_scheme(DATA_DIR, house, base_scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    gpath = _geom_path(house)
    if not gpath.exists():
        return JSONResponse(status_code=404, content={"error": f"project {house!r} 缺 geometry"})
    # 每日次数闸 (BudgetExceeded -> 402 handler); 计次即扣, 防失败重试刷量。
    _budget.reserve_furnish()
    model = body.get("model")

    def _generate() -> dict:
        scheme_meta = scheme_store.get_scheme(DATA_DIR, house, base_scheme_id)
        baseline_id = scheme_meta.get("baseline_version_id") or "v1"
        G = baseline_store.read_baseline_geometry(DATA_DIR, house, str(baseline_id))
        # 软装重构 Phase C-2: AI 对 base_scheme 的锁定布局做风格候选 (不落位)。
        base_furniture = scheme_store.read_furniture(DATA_DIR, house, base_scheme_id)
        provider = get_provider(_settings)
        # chat token 用量并入 /api/ai/status 计量 (审计: furnish 曾完全绕过预算/计量)。
        provider.on_usage = _budget.record_tokens
        result = furnish_service.generate_candidates(
            G,
            provider,
            base_furniture=base_furniture,
            style_prompt=style_prompt.strip(),
            count=count,
            base_scheme_id=base_scheme_id,
            model=model,
        )
        summaries = []
        for idx, candidate in enumerate(result["schemes"], start=1):
            scheme_id = _ai_scheme_id(idx)
            meta = scheme_store.create_scheme(
                DATA_DIR,
                house,
                {
                    "id": scheme_id,
                    "name": candidate["name"],
                    "source": "ai",
                    "style_prompt": candidate["style_prompt"],
                    "base_scheme_id": candidate["base_scheme_id"],
                    "furniture": candidate["furniture"],
                    # 溯源 (审计 P2-6): 此前 model/告警只在内存 job, 重启即丢。
                    "model": model or _settings.chat_model,
                    "furnish_warnings": result["warnings"],
                    "catalog_rev": catalog.CATALOG_REV,
                },
            )
            summaries.append(
                {
                    "id": meta["id"],
                    "name": meta["name"],
                    "items": len(candidate["furniture"]),
                }
            )
        return {"schemes": summaries, "warnings": result["warnings"]}

    job_id = _jobs.submit(
        _generate, meta={"house": house, "kind": "furnish", "base_scheme_id": base_scheme_id}
    )
    return {"job_id": job_id}


# 显式 MIME (修复: FileResponse 默认靠 mimetypes.guess_type, 容器 mimetypes 库缺 .webp ->
# 返回 application/octet-stream, 叠加 nosniff 后浏览器拒渲染 -> 所有 webp 缩略图 (空房照/AI
# 效果图) 空白。故按扩展名显式给 Content-Type; resolve 白名单已保证只服图片。
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


def _image_media_type(path) -> str:
    ext = os.path.splitext(str(path))[1].lower()
    return _IMAGE_MEDIA_TYPES.get(ext, "application/octet-stream")


@app.get("/api/artifacts/{rel_path:path}")
def get_artifact(rel_path: str):
    """同源服务生成产物 (uuid 不可变, 可长缓存)。防穿越: resolve 越界 -> 404。"""
    target = _artifacts.resolve(rel_path)
    if target is None:
        return JSONResponse(status_code=404, content={"error": "artifact not found"})
    resp = FileResponse(str(target), media_type=_image_media_type(target))
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["X-Content-Type-Options"] = "nosniff"  # 禁 MIME 嗅探 (防内联脚本)
    return resp


@app.get("/api/uploads/{rel_path:path}")
def get_upload(rel_path: str):
    """同源服务用户上传图 (第6步空房照)。防穿越同 artifacts。"""
    target = _uploads.resolve(rel_path)
    if target is None:
        return JSONResponse(status_code=404, content={"error": "upload not found"})
    resp = FileResponse(str(target), media_type=_image_media_type(target))
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["X-Content-Type-Options"] = "nosniff"  # 禁 MIME 嗅探 (防内联脚本)
    return resp


# 上传图 (第6步: 空房实拍照). 仅图片类型; 存 UPLOADS_DIR/{house}/empty/。
# 上传一律经 imaging.normalize_photo 归一化为 JPEG (验真身/物化 EXIF 方向/剥 GPS/压边),
# 故落盘扩展名恒为 jpg; 白名单仅做早拒, 真正的格式门 = Pillow 解码。
_UPLOAD_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
if imaging.HEIF_SUPPORTED:  # iPhone 默认格式, 依赖可用时开放
    _UPLOAD_EXT["image/heic"] = "jpg"
    _UPLOAD_EXT["image/heif"] = "jpg"
# 与宿主 nginx client_max_body_size 15m 对齐 (避免 15-20MB 合法上传被 nginx 裸 413 拦掉)。
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


# 裸上传端点已退役 (审计 P2-2): 落盘不登记任何 json, 每次调用即孤儿文件;
# 第6步照片一律走 /baselines/{version}/photos (登记 photos.json + 配额)。


# --------------------------------------------------------------------------- #
#  第5步: 轴测 photo 底图 -> gpt-image-2 img2img -> 照片级轴测效果图 (Phase 2)
# --------------------------------------------------------------------------- #
def _render_ai_response(
    house: str, scheme_id: str, payload: Optional[dict] = None
) -> dict | JSONResponse:
    """异步生成 (返 job_id, 前端轮询 /api/ai/jobs/{id})。

    同步段 (快, 线程池): 校验 -> 渲染 photo 轴测 SVG -> 栅格 PNG -> 组装提示词 -> 预扣预算。
    异步段 (慢 ~90-225s, job 线程): 调 gpt-image-2 -> 落产物 -> 记历史; 失败退预扣。
    """
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        scheme_store.assert_can_generate_render(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    if not _settings.ai_enabled:
        return JSONResponse(
            status_code=503, content={"error": "AI 未配置 (缺 OPENAI_API_KEY / OPENAI_BASE_URL)"}
        )
    # 预扣预算 (超限抛 BudgetExceeded -> 402 handler); 同步段失败须 release 不留账。
    _budget.reserve(house)
    try:
        G, geo, furniture, _scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        validation = scene.get("validation", {})
        if not validation.get("ok", False):
            detail = {
                "ok": False,
                "error": "场景校验未通过，已阻断 AI 出图",
                "validation": validation,
            }
            raise ValueError(json.dumps(detail, ensure_ascii=False))
        geom = axon.geom_bundle(G, geo)
        svg = axon.render(geom, scene["axon_furniture"], mode="photo")  # 写实轴测底图
        # 审计 P0-4: 底图纵横比随户型 bbox 变化, 与 edits size 错配会让模型重取景。
        # 按 viewBox 选最近输出档并 letterbox 到精确画布, 栅格与 edit 尺寸单一来源。
        edit_size = pick_edit_size_for_svg(svg)
        base_png = svg_to_png_canvas(svg, edit_size)
        # 1.5b 房内方位 + 审计 P0-6: 方案风格意向贯通到出图提示词 (无则回退默认现代轻奢)。
        # P1-8: 方位短语用「调整后」坐标 (与底图一致), 且与底图同样排除悬挂件。
        style = (_scheme_meta.get("style_prompt") or "").strip() or None
        # 结构化设计 Brief (B3): 与 style 同源自方案 meta, 编译进 prompt head (None 不改字节)。
        brief = _scheme_meta.get("brief")
        prompt_items = _prompt_items_from_axon(scene["axon_furniture"], G)
        prompt = prompt_gen.generate(
            prompt_items, G, with_positions=True, style=style, brief=brief
        )
        manifest = axon.render_manifest(scene, mode="axon-photoreal", prompt=prompt)
    except Exception as exc:  # noqa: BLE001 — 同步段失败: 退预扣, 显式 500
        _budget.release(house)
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        if isinstance(exc, ValueError):
            try:
                payload = json.loads(str(exc))
                if isinstance(payload, dict) and payload.get("validation"):
                    return JSONResponse(status_code=409, content=payload)
            except json.JSONDecodeError:
                pass
        return JSONResponse(status_code=500, content={"error": f"底图/提示词生成失败: {exc}"})

    model = (payload or {}).get("model") or _settings.model

    def _generate() -> dict:
        provider = get_provider(_settings)
        size_str = f"{edit_size[0]}x{edit_size[1]}"
        try:
            res = provider.edit(prompt, [base_png], size=size_str, model=model)
        except Exception:
            _budget.release(house)  # 生成失败退预扣
            raise
        _budget.record_tokens(res.usage)
        # P1: provider 实际返回图尺寸可能与请求档不一致, 读回真实宽高 -> record.actual_size,
        # 下游 (对比/画布/下载) 用真实尺寸而非请求档; 读失败回退请求档不阻断出图。
        actual_size = size_str
        try:
            _aw, _ah = imaging.read_size(res.data)
            actual_size = f"{_aw}x{_ah}"
        except Exception:  # noqa: BLE001
            pass
        rel = _artifacts.save_scoped(
            res.data,
            project_id=house,
            scope_id=scheme_id,
            kind=RENDER_MODES[AXON_PHOTOREAL]["artifact_kind"],
            ext="png",
        )
        # 复现链 (审计 P1-1): 归档底图 + prompt 原文 + 时间/引擎版本 —— 引擎演进后
        # 历史出图仍可精确复现与排查 (此前只有 hash, 只能报警不能还原)。
        base_rel = _artifacts.save_scoped(
            base_png,
            project_id=house,
            scope_id=scheme_id,
            kind=RENDER_MODES[AXON_PHOTOREAL]["base_kind"],
            ext="png",
        )
        # 缩略图 (审计 P2-3): 列表页 320px webp, 不再直载 1536 原 PNG; 失败不阻断出图。
        thumb_url = None
        try:
            thumb_rel = _artifacts.save_scoped(
                imaging.make_thumb(res.data),
                project_id=house,
                scope_id=scheme_id,
                kind="ai-thumb",
                ext="webp",
            )
            thumb_url = f"/api/artifacts/{thumb_rel}"
        except Exception:  # noqa: BLE001
            pass
        # 中等预览 (效果图页主图用, ~几百 KB webp; 全尺寸 PNG 只留下载)。
        preview_url = None
        try:
            preview_rel = _artifacts.save_scoped(
                imaging.make_preview(res.data),
                project_id=house,
                scope_id=scheme_id,
                kind="ai-preview",
                ext="webp",
            )
            preview_url = f"/api/artifacts/{preview_rel}"
        except Exception:  # noqa: BLE001
            pass
        record = {
            "id": rel.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "url": f"/api/artifacts/{rel}",
            "thumb_url": thumb_url,
            "preview_url": preview_url,
            "mode": AXON_PHOTOREAL,
            "size": size_str,  # 向后兼容: = 请求档 (requested_size)
            "requested_size": size_str,
            "actual_size": actual_size,
            "scheme_id": scheme_id,
            "model": res.model,
            "with_positions": True,
            # P1 可复现: 本次出图用的方案风格快照 (None=回退默认); 方案 style_prompt 后续被改也不影响历史。
            "style_snapshot": style,
            # B3 可复现: 本次出图用的结构化 Brief 快照 (None=未填)。
            "brief_snapshot": brief,
            "prompt": prompt,
            "base_url": f"/api/artifacts/{base_rel}",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine_version": APP_VERSION,
            "usage": res.usage,
            "scene_manifest": manifest,
        }
        scheme_store.append_render(DATA_DIR, house, scheme_id, record)
        return record

    job_id = _jobs.submit(
        _generate, meta={"house": house, "scheme_id": scheme_id, "kind": "ai-render"}
    )
    return {"job_id": job_id}


def _list_default_renders(house: str) -> list[dict]:
    """合并方案级与多方案上线前的默认效果图历史，并按 id/url 去重。"""
    current = scheme_store.list_renders(DATA_DIR, house, "default")
    legacy = _renders.list(house)
    merged: list[dict] = []
    seen: set[str] = set()
    for record in [*current, *legacy]:
        if not isinstance(record, dict):
            continue
        key = str(record.get("id") or record.get("url") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(record)
    return merged


@app.post("/api/projects/{house}/render-ai")
def render_ai(house: str, payload: Optional[dict] = Body(default=None)):
    return _render_ai_response(house, "default", payload)


@app.post("/api/projects/{house}/schemes/{scheme_id}/render-ai")
def render_scheme_ai(
    house: str, scheme_id: str, payload: Optional[dict] = Body(default=None)
):
    return _render_ai_response(house, scheme_id, payload)


# --------------------------------------------------------------------------- #
#  第7步: 空房实拍照 + 轴测参考 -> gpt-image-2 多图 img2img -> 实拍效果图
# --------------------------------------------------------------------------- #
# 拍摄视角 -> 轴测四分之一圈旋转 (实拍对齐)。v0=不旋转(与旧一致); v1/v2/v3=90/180/270°。
# 旧值 N/S/E/W 或 None -> 0 (不旋转), 读时安全。
_VIEW_TURNS = {"v0": 0, "v1": 1, "v2": 2, "v3": 3}


def _view_quarter_turns(direction) -> int:
    return _VIEW_TURNS.get(direction or "", 0)


# 相机相对落位 (问题2 解法): 轴测几何常与真实房间比例对不上, 故除了旋转对齐的参考图,
# 再把每件家具"相对镜头靠哪面墙"用文字讲清 —— AI 按语义落位, 不必像素级对齐轴测图。
_CW_COMPASS = {"north": "east", "east": "south", "south": "west", "west": "north"}


def _rotate_compass(d: str, k: int) -> str:
    for _ in range(k % 4):
        d = _CW_COMPASS[d]
    return d


def _furniture_ns_ew(it: dict, rect) -> tuple[str, str]:
    """家具在房内的三等分方位 (与 prompt_gen._zone_phrase 同规则) -> (ns, ew)。"""
    rw, rh = float(rect[2]), float(rect[3])
    if "dcx" in it or "dcy" in it:
        cx, cy = it.get("dcx", 0) or 0, it.get("dcy", 0) or 0
    else:
        cx = (it.get("dx", 0) or 0) + (it.get("w", 0) or 0) / 2
        cy = (it.get("dy", 0) or 0) + (it.get("h", 0) or 0) / 2
    ns = "north" if cy < rh / 3 else ("south" if cy > 2 * rh / 3 else "")
    ew = "west" if cx < rw / 3 else ("east" if cx > 2 * rw / 3 else "")
    return ns, ew


def _camera_zone_phrase(ns: str, ew: str, k: int) -> str:
    """(ns,ew) 经视角 k 旋转后 -> 相机相对落位中文短语。镜头从近角看向里角:
    投影下 west 墙在画面左、north 墙在画面右(里)、east 近右、south 近左。"""
    dirs = set()
    if ns:
        dirs.add(_rotate_compass(ns, k))
    if ew:
        dirs.add(_rotate_compass(ew, k))
    if not dirs:
        return "居中"
    if dirs == {"north", "west"}:
        return "画面里侧、左右墙交汇的后角"
    if dirs == {"south", "east"}:
        return "画面最前、贴近镜头的近角"
    if dirs == {"north", "east"}:
        return "画面右侧"
    if dirs == {"south", "west"}:
        return "画面左侧"
    d = next(iter(dirs))
    return {
        "west": "沿画面左侧墙",
        "north": "沿画面右(里)侧墙",
        "east": "沿画面右侧、靠近镜头处",
        "south": "沿画面左侧、靠近镜头处",
    }[d]


# 电视墙件: 电视柜/电视贴实墙构成电视墙, 沙发正对之。关系锚比三等分可靠 (Phase1 落位止血)。
_TV_WALL_TYPES = ("media", "tv")


def _nearest_wall(it: dict, rect) -> str:
    """家具中心 (房内相对坐标) 到四边最近的墙 N/S/E/W (纯几何, 不涉朝向/窗)。

    贴墙大件 (电视柜) 的最近墙即其靠墙 —— 比 _furniture_ns_ew 的三等分中心判定精确 (三等分
    会把贴东墙的电视柜误判成"东南角")。故意不读 orient: legacy 数据 orient 语义不一致不可信。"""
    rw, rh = float(rect[2]), float(rect[3])
    if "dcx" in it or "dcy" in it:
        cx, cy = it.get("dcx", 0) or 0, it.get("dcy", 0) or 0
    else:
        cx = (it.get("dx", 0) or 0) + (it.get("w", 0) or 0) / 2
        cy = (it.get("dy", 0) or 0) + (it.get("h", 0) or 0) / 2
    dist = {"N": cy, "S": rh - cy, "W": cx, "E": rw - cx}
    return min(dist, key=dist.get)


def _wall_cam_phrase(wall: str, k: int) -> str:
    """绝对墙向 N/S/E/W 经拍摄视角 k 旋转 -> 相机相对短语 (镜头 SE->NW, 同 _camera_zone_phrase)。"""
    compass = {"N": "north", "S": "south", "E": "east", "W": "west"}
    d = _rotate_compass(compass.get(wall, "north"), k)
    return {
        "west": "画面左侧墙",
        "north": "画面里侧墙",
        "east": "画面右侧墙",
        "south": "画面近侧墙",
    }[d]


def _camera_placement_summary(items: list, G: dict, k: int) -> str:
    """把该房各家具的相机相对落位拼成一句 (只列有房间 rect 的件)。

    Phase1 (弃用不可信 orient, 改纯几何关系锚): 电视柜/电视取【最近实墙】构成电视墙, 沙发只给
    "正对电视柜"关系锚而不谈自身靠墙 —— 直接绕开三等分把沙发误判贴南 (景观区落地窗侧) 的缺陷;
    其余家具保留三等分描述 (无电视柜的房逐字节不变, 保护既有基线)。"""
    rects = {r.get("id"): r.get("rect") for r in G.get("rooms", [])}
    tv = next(
        (it for it in items if it.get("t") in _TV_WALL_TYPES and rects.get(it.get("room_id"))),
        None,
    )
    tv_wall = _nearest_wall(tv, rects[tv["room_id"]]) if tv else None
    parts = []
    sofa_anchored = False
    for it in items:
        rect = rects.get(it.get("room_id"))
        t = it.get("t")
        if not rect or not t:
            continue
        if t in _TV_WALL_TYPES:
            parts.append(
                f"{t}(电视柜/电视): 紧贴{_wall_cam_phrase(_nearest_wall(it, rect), k)}实墙, 构成电视墙"
            )
            continue
        if t == "sofa" and tv_wall:
            if sofa_anchored:
                continue  # L 形沙发多件只出一次关系锚, 免重复
            parts.append(
                f"sofa(沙发): 正对电视柜、面向{_wall_cam_phrase(tv_wall, k)}, 靠背贴实墙不得贴落地窗"
            )
            sofa_anchored = True
            continue
        ns, ew = _furniture_ns_ew(it, rect)
        parts.append(f"{t}: {_camera_zone_phrase(ns, ew, k)}")
    return "; ".join(parts)


def _real_render_prompt(
    photo: dict,
    furniture: list,
    G: dict,
    *,
    scope: str = "house",
    style: Optional[str] = None,
    brief: Optional[dict] = None,
) -> str:
    """实拍效果图提示词: 保第一张照片的真实房间结构, 按第二张轴测参考完成软装。

    style (P0 贯通第7步): 方案 style_prompt 意向。区分硬装保护与软装风格 —— 风格只影响
    可移动软装 (家具款式/材质、窗帘、地毯、灯具、挂画、绿植、摆件), 不改建筑结构、门窗、
    地面/墙面固定材质、相机透视与自然光。style=None 时与旧字节一致 (保护既有基线)。"""
    room_hint = ""
    rid = photo.get("room_id")
    if rid:
        rooms = {r.get("id"): r for r in G.get("rooms", [])}
        room = rooms.get(rid)
        if room:
            name = (room.get("label") or {}).get("zh") or str(rid)
            types = sorted(
                {
                    str(it.get("t"))
                    for it in furniture
                    if it.get("room_id") == rid and it.get("t")
                }
            )
            if types:
                room_hint = f"这张照片拍摄的是{name}, 该房间的方案家具: {', '.join(types)}。"
            else:
                room_hint = f"这张照片拍摄的是{name}。"
    # 拍摄视角对齐 (实拍对齐升级): 轴测已按所选视角旋转到与照片同侧的"角", 故提示词从
    # 含糊的"照片朝X拍摄"改为"参考图已对齐, 请按图中家具紧贴的墙面一一对应摆放"。
    aligned = photo.get("direction") in _VIEW_TURNS
    align_hint = ""
    if aligned:
        align_hint = (
            "第二张轴测参考图已按这张照片的拍摄视角旋转对齐 —— 请把每件家具摆到与参考图中"
            "相同的墙面与角落 (正对镜头的墙、左手墙、右手墙一一对应), 而不是仅凭大致印象。"
        )
        # 相机相对落位 (问题2): 轴测比例可能对不上真实房间, 故再用文字点明每件靠哪面墙。
        if scope == "room":
            placement = _camera_placement_summary(
                furniture, G, _view_quarter_turns(photo.get("direction"))
            )
            if placement:
                align_hint += f" 各家具相对你镜头的落位: {placement}。"
    reference_hint = (
        "第二张图是这个房间的软装方案轴测参考图。"
        if scope == "room"
        else "第二张图是整套户型软装方案的轴测参考图, 请找到照片对应的房间。"
    )
    # 风格软锁 (P0): 方案风格只作用于可移动软装, 硬装/结构/透视/自然光一律保持第一张照片不变。
    style_hint = ""
    if style:
        style_hint = (
            f" 目标软装风格: {style}。此风格只影响可移动软装 —— 家具款式与材质、窗帘、地毯、"
            "灯具、挂画、绿植、摆件的配色与质感; 不得改变第一张照片的固定硬装 (墙体、门窗、"
            "地面与墙面基础材质)、建筑结构、相机透视与自然光。"
        )
    # 设计 Brief 片段 (B3): 结构化需求编译成英文指令, 与 style 同属软装约束, 拼在 style_hint
    # 之后; brief 空时为空串 -> 与旧字节一致 (保护既有基线)。
    brief_frag = brief_prompt.compile_brief(brief)
    brief_hint = f" {brief_frag}" if brief_frag else ""
    return (
        "第一张图是房间的空房实拍照片, "
        + reference_hint
        + "严格保持第一张照片的房间结构、门窗位置、墙面地面材质、透视与自然光照不变, "
        "按照轴测参考图中该房间的家具布局、款式与配色, 在照片中完成软装摆放。"
        "输出照片级真实感的室内实拍效果图, 不要改变相机角度。"
        # 落位安全规则 (防"床顶窗"类缺陷): 大件背面贴实墙, 不贴玻璃/落地窗, 不悬在房中央。
        "床、沙发、衣柜、电视柜等大件家具的背面必须紧贴实体墙摆放, "
        "严禁把大件家具正面或床头/靠背贴合落地窗、玻璃幕墙, 也不要让大件悬在房间正中央。"
        + room_hint
        + align_hint
        + style_hint
        + brief_hint
    )


_WALL_SIDES_ORDER = ("N", "S", "E", "W")


def _resolve_wall_material_photos(
    G: dict, photos: list[dict], room_id_filter: Optional[str], cap: int
) -> list[tuple[str, bytes]]:
    """墙面材质C: 从 G.rooms[].walls[side].photo_id 收集实拍参考图字节 (注入 img2img edits)。

    确定性顺序 (同场景永远同参考集): 房间声明序 -> 边序 N,S,E,W; 按 photo_id 去重 (取首现);
    room_id_filter 非空时只收该房 (与第7步按房切片一致)。解析失败/缺文件的静默跳过 (不阻断出图)。
    返回 [(photo_id, bytes)], 至多 cap 个。
    """
    if cap <= 0:
        return []
    by_id = {p.get("id"): p for p in photos}
    seen: set[str] = set()
    out: list[tuple[str, bytes]] = []
    for room in G.get("rooms", []):
        if room_id_filter is not None and str(room.get("id")) != str(room_id_filter):
            continue
        walls = room.get("walls")
        if not isinstance(walls, dict):
            continue
        for side in _WALL_SIDES_ORDER:
            finish = walls.get(side)
            pid = finish.get("photo_id") if isinstance(finish, dict) else None
            if not pid or pid in seen:
                continue
            entry = by_id.get(pid)
            if not entry:
                continue
            url = str(entry.get("url") or "")
            rel = url[len("/api/uploads/"):] if url.startswith("/api/uploads/") else ""
            tgt = _uploads.resolve(rel) if rel else None
            if tgt is None:
                continue
            try:
                data = tgt.read_bytes()
            except OSError:
                continue
            seen.add(pid)
            out.append((pid, data))
            if len(out) >= cap:
                return out
    return out


def _geometry_lock_prompt(legend: list, furniture: list, style: Optional[str]) -> str:
    """几何锁定实拍 prompt (英文, nano-banana 双图编辑): 颜色盒 -> 家具映射。

    legend 来自 perspective.annotate_boxes ([{"color","t","count"}]); 图1=空房照,
    图2=彩盒标注。形体要求写死 (立体、按盒的占地/高度/朝向), 修 flux inpaint 平 mask
    只画矮物的顽疾。生产验证过的两个坑写进指令: 盒色仅是标记 (否则沙发被画成蓝色),
    画幅边缘被裁的盒也必须替换 (否则残留半个彩盒)。
    """
    parts: list[str] = []
    for entry in legend:
        en = (catalog.CATALOG.get(entry["t"]) or {}).get("en") or entry["t"]
        count = int(entry.get("count") or 1)
        if count > 1:
            parts.append(f"{entry['color']} boxes = {en} ({count} pieces, one per box)")
        else:
            parts.append(f"{entry['color']} box = {en}")
    mapping = "; ".join(parts) if parts else "the scheme furniture"
    style_txt = style or "modern light-luxury (现代轻奢)"
    rug_txt = (
        " Add an area rug on the floor under the seating."
        if any(it.get("t") == "rug" for it in furniture)
        else ""
    )
    return (
        "Image 1 is a real photo of an empty room. Image 2 is the same photo with colored "
        "translucent boxes marking where furniture must be placed. Produce a photorealistic "
        f"version of image 1 furnished exactly according to image 2's layout: {mapping}. "
        "Each piece must be a real, solid, three-dimensional piece of furniture that fills its "
        f"box's footprint, height and orientation, in {style_txt} style. The box colors are "
        "position markers only — do NOT use them as furniture colors; choose realistic "
        "materials fitting the style."
        + rug_txt
        + " Keep image 1's camera angle, walls, windows, floor, ceiling, materials and lighting "
        "exactly unchanged, and add realistic floor reflections and contact shadows under the "
        "new furniture. Every colored box must be erased and replaced by its furniture, "
        "including boxes partially cut off at the image edge; the output must contain no "
        "colored boxes, overlays or text — only real furniture."
    )


def _render_real_geometry_lock(
    house: str, scheme_id: str, photo: dict, backend: str | None = None
) -> dict | JSONResponse:
    """路线A 几何锁定实拍: 空房照 + 彩盒标注图 (透视标定投影) -> 双图指令编辑。

    落位/形体由标注盒约束 (体量以画面像素进图), 替代轴测软参考与平 mask inpaint (只画
    矮物)。编辑后端 GEOMETRY_EDIT_BACKEND: relay=gpt-image-2 (默认; A/B 质量持平且分辨率
    更高、relay 成本更低) / fal=nano-banana; 请求级 backend 参数可单次覆盖 (换后端重试)。
    产物 method=geometry-lock。输出为模型重绘整图 (结构由模型保持, 不做 mask 硬合成 ——
    家具溢出盒区会被裁碎)。
    """
    # backend 由调用方 (_render_real_response) 归一化后传入; 兜底再钳一次防直调。
    edit_backend = "fal" if backend == "fal" else "relay"
    url = str(photo.get("url") or "")
    rel = url[len("/api/uploads/"):] if url.startswith("/api/uploads/") else ""
    target = _uploads.resolve(rel) if rel else None
    if target is None:
        return JSONResponse(status_code=404, content={"error": "照片文件不存在或不可读"})
    empty_png = target.read_bytes()

    _budget.reserve(house)
    try:
        G, geo, furniture, scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        validation = scene.get("validation", {})
        if not validation.get("ok", False):
            raise ValueError(json.dumps(
                {"ok": False, "error": "场景校验未通过，已阻断 AI 出图", "validation": validation},
                ensure_ascii=False,
            ))
        cal = photo["calibration"]
        cam = perspective.Camera.from_dict(cal["camera"])
        img_wh = (int(cal["img_wh"][0]), int(cal["img_wh"][1]))
        rooms_by_id = {r["id"]: r["rect"] for r in G["rooms"]}
        rid = photo.get("room_id")
        if rid:
            try:
                members = set(axon.merge_group_ids(G, str(rid)))
            except Exception:  # noqa: BLE001 - 房间已删/改名: 退回全屋家具
                members = {rid}
            furn = [it for it in furniture if it.get("room_id") in members]
        else:
            furn = list(furniture)
        mm_per_px = (G.get("meta", {}) or {}).get("mm_per_px", 10)
        guide_png, legend, drawn = perspective.annotate_boxes(
            cam, furn, rooms_by_id, empty_png, img_wh, mm_per_px=mm_per_px
        )
        if drawn == 0:
            raise ValueError("该照片房间无可投影家具 (标注盒为空); 请检查方案家具与标定")
        style = (scheme_meta.get("style_prompt") or "").strip() or None
        brief = scheme_meta.get("brief")
        prompt = _geometry_lock_prompt(legend, furn, style)
        brief_frag = brief_prompt.compile_brief(brief)
        if brief_frag:
            prompt = f"{prompt} {brief_frag}"
        manifest = axon.render_manifest(scene, mode="real-photo", prompt=prompt)
    except Exception as exc:  # noqa: BLE001 — 同步段失败: 退预扣
        _budget.release(house)
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        if isinstance(exc, ValueError):
            try:
                detail = json.loads(str(exc))
                if isinstance(detail, dict) and detail.get("validation"):
                    return JSONResponse(status_code=409, content=detail)
            except json.JSONDecodeError:
                pass
        return JSONResponse(status_code=500, content={"error": f"标注图/提示词生成失败: {exc}"})

    def _edit_once(gen_prompt: str) -> tuple:
        # 两后端吃同一套 [空房照, 彩盒标注] 双图引导, 只换执行模型。
        if edit_backend == "fal":
            size_str = f"{img_wh[0]}x{img_wh[1]}"  # fal 不收尺寸参数, 请求档记照片档
            res = get_fal_provider(_settings).edit(gen_prompt, [empty_png, guide_png])
        else:
            # relay 按照片纵横比选输出档 (比例不符会让模型重取景, 违反保结构)。
            edit_size = pick_edit_size(img_wh[0], img_wh[1])
            size_str = f"{edit_size[0]}x{edit_size[1]}"
            res = get_provider(_settings).edit(
                gen_prompt, [empty_png, guide_png], size=size_str, model=_settings.model
            )
        return res, size_str

    def _generate() -> dict:
        # P4 自动验收环: 出图 -> evaluate -> 不过关带修正指令重试 (每次重试另行预扣,
        # 预算不够即止)。软门: 重试用尽仍不过关, 交付得分最高的一张并记 auto_check。
        attempts: list[dict] = []
        try:
            res, size_str = _edit_once(prompt)
        except Exception:
            _budget.release(house)  # 首次生成失败: 退预扣, 保持旧语义 (job 报错)
            raise
        _budget.record_tokens(res.usage or {})
        max_retries = max(0, _settings.geometry_accept_max_retries)
        verdict = None
        for retry in range(max_retries + 1):
            if _settings.geometry_accept:
                try:
                    verdict = acceptance.evaluate_geometry_lock(
                        empty_png, res.data, guide_png=guide_png, cam=cam, furniture=furn,
                        rooms_by_id=rooms_by_id, img_wh=img_wh, mm_per_px=mm_per_px,
                    )
                except Exception as exc:  # noqa: BLE001 - 验收自身出错不阻断交付
                    verdict = {"ok": True, "error": f"验收执行失败: {exc}"}
            else:
                verdict = {"ok": True, "skipped": True}
            attempts.append({"res": res, "size_str": size_str, "verdict": verdict})
            if verdict["ok"] or retry >= max_retries:
                break
            try:
                _budget.reserve(house)  # 重试是新的一张图: 独立预扣
            except Exception:  # noqa: BLE001 - 预算不够: 停止重试, 用已有最佳
                break
            try:
                res, size_str = _edit_once(prompt + acceptance.retry_hint(verdict))
            except Exception:  # noqa: BLE001 - 重试失败: 退这次预扣, 用已有最佳
                _budget.release(house)
                break
            _budget.record_tokens(res.usage or {})
        best = max(
            attempts,
            key=lambda a: (a["verdict"]["ok"], a["verdict"].get("score", 1.0)),
        )
        res, size_str = best["res"], best["size_str"]
        auto_check = {
            k: v for k, v in best["verdict"].items() if k != "checks"
        }  # 记录瘦身: 明细 checks 不落盘, 失败原因/分数够溯源
        auto_check["attempts"] = len(attempts)
        actual_size = size_str
        try:
            _aw, _ah = imaging.read_size(res.data)
            actual_size = f"{_aw}x{_ah}"
        except Exception:  # noqa: BLE001
            pass
        rel_out = _artifacts.save_scoped(
            res.data, project_id=house, scope_id=scheme_id,
            kind=RENDER_MODES[REAL_PHOTO]["artifact_kind"], ext="png",
        )
        base_rel = _artifacts.save_scoped(  # 归档彩盒标注图作复现底
            guide_png, project_id=house, scope_id=scheme_id,
            kind=RENDER_MODES[REAL_PHOTO]["base_kind"], ext="png",
        )
        thumb_url = None
        try:
            thumb_rel = _artifacts.save_scoped(
                imaging.make_thumb(res.data), project_id=house, scope_id=scheme_id,
                kind="real-thumb", ext="webp")
            thumb_url = f"/api/artifacts/{thumb_rel}"
        except Exception:  # noqa: BLE001
            pass
        preview_url = None
        try:
            preview_rel = _artifacts.save_scoped(
                imaging.make_preview(res.data), project_id=house, scope_id=scheme_id,
                kind="real-preview", ext="webp")
            preview_url = f"/api/artifacts/{preview_rel}"
        except Exception:  # noqa: BLE001
            pass
        record = {
            "id": rel_out.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "url": f"/api/artifacts/{rel_out}",
            "thumb_url": thumb_url,
            "preview_url": preview_url,
            "mode": REAL_PHOTO,
            "method": "geometry-lock",  # 路线A: 区分 gpt-image-2 轴测软参考的历史记录
            "form_guidance": "anno-box-edit",  # 形体提质: 彩盒标注+指令编辑 (区分早期 footprint-mask inpaint)
            "edit_backend": edit_backend,  # 生效编辑后端 (含请求级覆盖), 换后端重试溯源用
            "auto_check": auto_check,  # P4 自动验收 (与人工验收 status 字段互不相干)
            "scheme_id": scheme_id,
            "model": res.model,
            "size": size_str,
            "requested_size": size_str,
            "actual_size": actual_size,
            "photo_id": photo.get("id"),
            "photo_url": photo.get("url"),
            "photo_sha256": photo.get("sha256"),
            "room_id": photo.get("room_id"),
            "style_snapshot": style,
            "brief_snapshot": brief,
            "prompt": prompt,
            "guide_url": f"/api/artifacts/{base_rel}",
            "base_url": f"/api/artifacts/{base_rel}",
            "furniture_locked": drawn,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine_version": APP_VERSION,
            "usage": res.usage,
            "scene_manifest": manifest,
        }
        scheme_store.append_render(DATA_DIR, house, scheme_id, record)
        return record

    job_id = _jobs.submit(
        _generate, meta={"house": house, "scheme_id": scheme_id, "kind": "real-render"}
    )
    return {"job_id": job_id}


def _render_real_response(
    house: str, scheme_id: str, payload: Optional[dict] = None
) -> dict | JSONResponse:
    """第7步异步生成: 空房照 (真实结构锚点) + 轴测参考 (家具方案) -> 实拍效果图。

    同步段: 校验 -> 取照片字节 -> 渲染轴测参考 PNG -> 提示词 -> 预扣预算。
    异步段: provider.edit 多图 -> 落产物 (kind=real-render) -> 记方案历史; 失败退预扣。
    """
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        scheme_store.assert_can_generate_render(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    if not _settings.ai_enabled:
        return JSONResponse(
            status_code=503, content={"error": "AI 未配置 (缺 OPENAI_API_KEY / OPENAI_BASE_URL)"}
        )
    photo_id = (payload or {}).get("photo_id")
    if not isinstance(photo_id, str) or not photo_id.strip():
        return JSONResponse(status_code=400, content={"error": "photo_id 必须为非空字符串"})
    photo_id = photo_id.strip()

    # 照片归属 = 方案绑定的户型版本 (照片绑版本不绑方案 — §8.3)。
    try:
        scheme_meta = scheme_store.get_scheme(DATA_DIR, house, scheme_id)
        baseline_id = str(scheme_meta.get("baseline_version_id") or "v1")
        photos = baseline_store.list_photos(DATA_DIR, house, baseline_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    photo = next((p for p in photos if p.get("id") == photo_id), None)
    if photo is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"照片 {photo_id!r} 不存在 (户型 {baseline_id})"},
        )
    # P0 用途硬校验: 实拍底图必须是空房照 (purpose=empty 或历史缺省 null)。墙面材质/底图描摹
    # 等非空房照被误当结构锚点会高概率产废图并白烧额度, 故在预扣预算前直接 400 拦下。
    purpose = photo.get("purpose")
    if purpose not in (None, "empty"):
        return JSONResponse(
            status_code=400,
            content={
                "error": f"照片用途为 {purpose!r}, 只有空房照 (purpose=empty) 才能做实拍底图"
            },
        )
    # 请求级编辑后端覆盖 (换后端重试): 显式指定时严格校验, 不做静默回退 —— 用户点名 fal
    # 却落到别的路径会造成"以为换了后端"的误导; settings 级 fal 缺 key 的静默回退保持不变。
    backend = (payload or {}).get("backend")
    if backend is not None:
        if backend not in ("relay", "fal"):
            return JSONResponse(
                status_code=400, content={"error": "backend 仅支持 'relay' 或 'fal'"}
            )
        if not photo.get("calibration"):
            return JSONResponse(
                status_code=400,
                content={"error": "指定编辑后端仅对已标定照片的几何锁定出图生效, 请先完成透视标定"},
            )
        if backend == "fal" and not _settings.fal_enabled:
            return JSONResponse(
                status_code=400, content={"error": "fal 后端未配置 (缺 FAL_KEY), 无法切换"}
            )
    # 几何锁定路径 (路线A): 照片已标定透视 -> 彩盒标注引导, 落位/形体硬约束, 跳过
    # direction readiness gate (标定已精确定位)。编辑后端默认 relay (gpt-image-2, 凭据已由
    # 上方 ai_enabled 门保证); 配成 fal 时须 fal_enabled, 否则落到下方轴测软参考兼容路径。
    # 生效后端在此归一化一次 (env 非 "fal" 一律按 relay), 下游不再各自推导。
    effective_backend = "fal" if (backend or _settings.geometry_edit_backend) == "fal" else "relay"
    if photo.get("calibration") and (effective_backend != "fal" or _settings.fal_enabled):
        return _render_real_geometry_lock(house, scheme_id, photo, backend=effective_backend)
    # B2 readiness gate: 未标注拍摄房间 (room_id) 或视角 (direction) 时, 轴测参考会退回整宅/
    # 不旋转, 家具易串房间/贴错墙 —— 默认在预扣预算前 400 拦下。用户可显式 allow_unlabeled 降级
    # 为"低准确度模式"跳过 (记录里打 low_accuracy 溯源)。
    allow_unlabeled = bool((payload or {}).get("allow_unlabeled"))
    missing: list[str] = []
    if not photo.get("room_id"):
        missing.append("room_id")
    if photo.get("direction") not in _VIEW_TURNS:
        missing.append("direction")
    if missing and not allow_unlabeled:
        return JSONResponse(
            status_code=400,
            content={
                "error": "实拍生成需先标注拍摄房间与视角 (可切换低准确度模式跳过)",
                "code": "REAL_NOT_READY",
                "missing": missing,
            },
        )
    low_accuracy = bool(missing)  # 标注不全但已显式降级 -> 记录溯源
    url = str(photo.get("url") or "")
    rel = url[len("/api/uploads/"):] if url.startswith("/api/uploads/") else ""
    target = _uploads.resolve(rel) if rel else None
    if target is None:
        return JSONResponse(status_code=404, content={"error": "照片文件不存在或不可读"})
    empty_png = target.read_bytes()

    _budget.reserve(house)
    try:
        G, geo, furniture, _scheme_meta2, scene = _load_scheme_scene(house, scheme_id)
        validation = scene.get("validation", {})
        if not validation.get("ok", False):
            detail = {
                "ok": False,
                "error": "场景校验未通过，已阻断 AI 出图",
                "validation": validation,
            }
            raise ValueError(json.dumps(detail, ensure_ascii=False))
        geom = axon.geom_bundle(G, geo)
        axon_furniture = scene["axon_furniture"]
        # 审计 P0-3 (Phase1.5c): 照片标注了房间时按房切片参考图 —— 单间照片配单间轴测,
        # 避免目标房在整宅图中占比过小/邻房家具串扰; 未标注回退整宅。
        axon_scope = "house"
        rid = photo.get("room_id")
        if rid:
            try:
                # P3 异形: 目标房属 merge 组时切整组 (L 形整体), 家具按同一成员集过滤,
                # 与 slice 用同一 merge_group_ids 规则, 保证几何与家具一致不 dangling。
                member_ids = axon.merge_group_ids(G, str(rid))
                geom = axon.slice_geom_for_room(geom, str(rid))
                axon_furniture = [
                    it for it in axon_furniture if it.get("_room_id") in member_ids
                ]
                axon_scope = "room"
            except ValueError:
                axon_scope = "house"  # 房间已被删/改名: 回退整宅
        # 拍摄视角对齐 (实拍对齐): 按照片标注的视角把轴测绕房间中心转 90°×k, 让参考图
        # 从与照片同侧看进去, 家具落到对的墙 (v0/未标注=不旋转=与旧一致)。
        quarter_turns = _view_quarter_turns(photo.get("direction"))
        svg = axon.render(geom, axon_furniture, mode="photo", quarter_turns=quarter_turns)
        # 审计 P0-5: 输出尺寸跟随照片纵横比 (竖拍不再被压横幅); 参考图 letterbox 到同尺寸。
        edit_size = pick_edit_size(photo.get("width"), photo.get("height"))
        if not photo.get("width") or not photo.get("height"):
            # 旧照片条目无宽高元数据: 从字节读 (Pillow, 毫秒级)。
            try:
                import io as _io

                from PIL import Image as _Image

                with _Image.open(_io.BytesIO(empty_png)) as _im:
                    edit_size = pick_edit_size(_im.size[0], _im.size[1])
            except Exception:  # noqa: BLE001 - 读失败回退默认横幅
                pass
        axon_png = svg_to_png_canvas(svg, edit_size)
        # 材质C (P2): 收集本方案墙面实拍参考图 -> 注入 edits。保留 empty+axon 两槽, 余量
        # (≤2) 给墙面照; 按房切片时只取该房。确定性顺序, 缺文件静默跳过。
        wall_photos = _resolve_wall_material_photos(
            G, photos,
            str(rid) if (axon_scope == "room" and rid) else None,
            cap=max(0, MAX_EDIT_IMAGES - 2),
        )
        wall_photo_ids = [pid for pid, _ in wall_photos]
        # 风格软锁 (P0): 方案 style_prompt 贯通实拍 prompt (无则回退隐式靠轴测参考)。
        style = (_scheme_meta2.get("style_prompt") or "").strip() or None
        # 结构化设计 Brief (B3): 与 style 同源自方案 meta, 拼进实拍 prompt (None 不改字节)。
        brief = _scheme_meta2.get("brief")
        prompt = _real_render_prompt(
            photo,
            _prompt_items_from_axon(axon_furniture, G),
            G,
            scope=axon_scope,
            style=style,
            brief=brief,
        )
        manifest = axon.render_manifest(scene, mode="real-photo", prompt=prompt)
    except Exception as exc:  # noqa: BLE001 — 同步段失败: 退预扣, 显式回报
        _budget.release(house)
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        if isinstance(exc, ValueError):
            try:
                detail_payload = json.loads(str(exc))
                if isinstance(detail_payload, dict) and detail_payload.get("validation"):
                    return JSONResponse(status_code=409, content=detail_payload)
            except json.JSONDecodeError:
                pass
        return JSONResponse(status_code=500, content={"error": f"底图/提示词生成失败: {exc}"})

    model = (payload or {}).get("model") or _settings.model

    def _generate() -> dict:
        provider = get_provider(_settings)
        size_str = f"{edit_size[0]}x{edit_size[1]}"
        try:
            # 多图: 空房照在前 (结构锚点), 轴测参考次之 (家具方案), 墙面实拍参考 (材质C) 在后。
            edit_images = [empty_png, axon_png, *(b for _pid, b in wall_photos)]
            res = provider.edit(prompt, edit_images, size=size_str, model=model)
        except Exception:
            _budget.release(house)  # 生成失败退预扣
            raise
        _budget.record_tokens(res.usage)
        # P1: 读回 provider 实际返回图尺寸 (实测请求 1536x1024 -> 返回 1677x938);
        # 读失败回退请求档不阻断出图。
        actual_size = size_str
        try:
            _aw, _ah = imaging.read_size(res.data)
            actual_size = f"{_aw}x{_ah}"
        except Exception:  # noqa: BLE001
            pass
        rel_out = _artifacts.save_scoped(
            res.data,
            project_id=house,
            scope_id=scheme_id,
            kind=RENDER_MODES[REAL_PHOTO]["artifact_kind"],
            ext="png",
        )
        base_rel = _artifacts.save_scoped(
            axon_png,
            project_id=house,
            scope_id=scheme_id,
            kind=RENDER_MODES[REAL_PHOTO]["base_kind"],
            ext="png",
        )
        thumb_url = None
        try:
            thumb_rel = _artifacts.save_scoped(
                imaging.make_thumb(res.data),
                project_id=house,
                scope_id=scheme_id,
                kind="real-thumb",
                ext="webp",
            )
            thumb_url = f"/api/artifacts/{thumb_rel}"
        except Exception:  # noqa: BLE001
            pass
        # 中等预览 (效果图页主图用, ~几百 KB webp; 全尺寸 PNG ~2MB 只留下载)。
        preview_url = None
        try:
            preview_rel = _artifacts.save_scoped(
                imaging.make_preview(res.data),
                project_id=house,
                scope_id=scheme_id,
                kind="real-preview",
                ext="webp",
            )
            preview_url = f"/api/artifacts/{preview_rel}"
        except Exception:  # noqa: BLE001
            pass
        record = {
            "id": rel_out.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "url": f"/api/artifacts/{rel_out}",
            "thumb_url": thumb_url,
            "preview_url": preview_url,
            "mode": REAL_PHOTO,
            "scheme_id": scheme_id,
            "model": res.model,
            "size": size_str,  # 向后兼容: = 请求档 (requested_size)
            "requested_size": size_str,
            "actual_size": actual_size,
            "axon_scope": axon_scope,
            "photo_id": photo_id,
            "photo_url": photo.get("url"),
            "photo_sha256": photo.get("sha256"),
            "room_id": photo.get("room_id"),
            "direction": photo.get("direction"),  # 溯源: 本张用的拍摄视角 (v0..v3 / None)
            "wall_photo_ids": wall_photo_ids,  # 材质C: 注入 edits 的墙面参考图 (溯源/可复现)
            # P1 可复现: 本次出图用的方案风格快照 (None=回退隐式靠轴测参考)。
            "style_snapshot": style,
            # B3 可复现: 本次出图用的结构化 Brief 快照 (None=未填)。
            "brief_snapshot": brief,
            "prompt": prompt,
            "base_url": f"/api/artifacts/{base_rel}",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine_version": APP_VERSION,
            "usage": res.usage,
            "scene_manifest": manifest,
        }
        # B2: 低准确度模式 (未标注房间/视角但显式降级) 生成的记录打标溯源; 完整标注不加该键
        # (字节兼容既有记录)。
        if low_accuracy:
            record["low_accuracy"] = True
        scheme_store.append_render(DATA_DIR, house, scheme_id, record)
        return record

    job_id = _jobs.submit(
        _generate, meta={"house": house, "scheme_id": scheme_id, "kind": "real-render"}
    )
    return {"job_id": job_id}


@app.post("/api/projects/{house}/schemes/{scheme_id}/render-real")
def render_scheme_real(
    house: str, scheme_id: str, payload: Optional[dict] = Body(default=None)
):
    return _render_real_response(house, scheme_id, payload)


_RECORD_HEAVY_KEYS = ("scene_manifest", "usage", "prompt")


def _shape_render_records(records: list, detail: int, limit: int | None) -> list:
    """列表读侧瘦身 (审计 P2-3): manifest/usage/prompt 占载荷 3/4 且列表页零消费。

    detail=1 保留全量 (排查/溯源用); limit 截断最新 N 条。"""
    if limit is not None and limit >= 0:
        records = records[:limit]
    if detail:
        return records
    return [
        {k: v for k, v in r.items() if k not in _RECORD_HEAVY_KEYS}
        if isinstance(r, dict)
        else r
        for r in records
    ]


@app.get("/api/projects/{house}/renders")
def list_renders(house: str, detail: int = 0, limit: Optional[int] = None):
    """AI 渲染历史 (最新在前)。默认剥重载荷; ?detail=1 全量, ?limit=N 截断。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        return _shape_render_records(_list_default_renders(house), detail, limit)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.get("/api/projects/{house}/schemes/{scheme_id}/renders")
def list_scheme_renders(
    house: str, scheme_id: str, detail: int = 0, limit: Optional[int] = None
):
    """AI 渲染历史 (最新在前)。默认剥重载荷; ?detail=1 全量, ?limit=N 截断。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        return _shape_render_records(
            scheme_store.list_renders(DATA_DIR, house, scheme_id), detail, limit
        )
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


# 效果图记录自有的 4 个 ARTIFACTS 文件键 (成品/底图/缩略图/预览)。
# 显式不含 photo_url —— 那是 UPLOADS 里 baselines/其它效果图共享的空房实拍照, 绝不可删。
_RENDER_OWN_FILE_KEYS = ("url", "base_url", "thumb_url", "preview_url")
_ARTIFACTS_URL_PREFIX = "/api/artifacts/"


def _unlink_render_files(record: dict) -> int:
    """删除一条 render 记录自有的产物文件 (幂等, 缺失即跳过); 返回实际删除文件数。"""
    removed = 0
    for key in _RENDER_OWN_FILE_KEYS:
        url = record.get(key)
        if not isinstance(url, str) or not url.startswith(_ARTIFACTS_URL_PREFIX):
            continue
        rel = url[len(_ARTIFACTS_URL_PREFIX):]
        path = _artifacts.resolve(rel)  # 防穿越 + 白名单, 越界返 None
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return removed


@app.delete("/api/projects/{house}/schemes/{scheme_id}/renders/{render_id}")
def delete_scheme_render(house: str, scheme_id: str, render_id: str):
    """删除一条效果图: 先摘记录 (方案级; default 另摘 legacy 账本防合并复活), 后 unlink
    该记录自有的 4 个产物文件 (排除共享 photo_url)。先记录后文件 —— 崩溃只留孤儿由 gc.sh 兜底。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        removed = scheme_store.remove_render(DATA_DIR, house, scheme_id, render_id)
        # default 方案历史合并了 legacy 账本, 须双摘; 取任一命中记录用于删文件。
        if scheme_id == "default":
            legacy = _renders.remove(house, render_id)
            removed = removed or legacy
        if removed is None:
            return JSONResponse(
                status_code=404, content={"error": f"效果图 {render_id!r} 不存在"}
            )
        files_removed = _unlink_render_files(removed)
        return {"ok": True, "deleted": render_id, "files_removed": files_removed}
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.patch("/api/projects/{house}/schemes/{scheme_id}/renders/{render_id}")
def patch_scheme_render(
    house: str, scheme_id: str, render_id: str, payload: dict = Body(...)
):
    """给一条效果图记录写验收/确认状态 (工作流改造 F): 实拍验收 (accepted/rejected) 与轴测
    确认为方案参考 (accepted) 共用此端点。body: {status, feedback_reason?}。未命中 404。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"error": "payload must be an object"})
    status = payload.get("status")
    if not isinstance(status, str):
        return JSONResponse(status_code=400, content={"error": "status 必须为字符串"})
    feedback_reason = payload.get("feedback_reason")
    try:
        updated = scheme_store.set_render_status(
            DATA_DIR, house, scheme_id, render_id, status,
            feedback_reason=feedback_reason,
        )
        # default 方案历史合并了 legacy 账本 (见 _list_default_renders); 方案级查不到时回退
        # legacy 账本改状态, 与 delete_scheme_render 的双账本回退对称 (否则老出图验收/确认必现 404)。
        if updated is None and scheme_id == "default":
            updated = _renders.set_status(
                house, render_id, status, feedback_reason=feedback_reason
            )
        if updated is None:
            return JSONResponse(
                status_code=404, content={"error": f"效果图 {render_id!r} 不存在"}
            )
        return updated
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
