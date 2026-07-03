# -*- coding: utf-8 -*-
"""阅天府软装 — 最小 FastAPI 后端 (Phase 0 walking skeleton)。

引擎接入: import floorplan_core (已 pip install -e packages/floorplan_core), 单一真源。
活编辑数据目录由 DATA_DIR(env) 指定, 默认基于 __file__ 相对推导到 data/projects/。
布局: {DATA_DIR}/{house}/geometry.json + {DATA_DIR}/{house}/furniture.json。
活数据已自引擎/红线目录 (轴测图POC) 迁出, 杜绝「测试期 save-geometry 误写红线参照」污染。
"""
from __future__ import annotations

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

from floorplan_core import axon, geometry, prompt_gen  # 引擎库 (单一真源)

from starlette.concurrency import run_in_threadpool

from aigc.artifacts import ArtifactStore  # AI 子系统 (Phase 1 基础设施)
from aigc.budget import BudgetGuard
from aigc.config import get_settings
from aigc import imaging
from aigc.errors import AIError, BudgetExceeded, ProviderError
from aigc.jobs import JobManager
from aigc.providers import get_provider
from aigc.raster import svg_to_png
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
        return baseline_store.save_baseline_geometry(DATA_DIR, house, version, G)
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
):
    """上传空房实拍照并登记到户型版本。文件复用 uploads 自托管 (kind=empty)。"""
    if GEOM_READONLY:
        return JSONResponse(
            status_code=403,
            content={"ok": False, "error": "GEOM_READONLY: baseline writes disabled"},
        )
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
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
        entry = {
            "id": uuid.uuid4().hex,
            "url": f"/api/uploads/{rel}",
            "room_id": room_id,
            "direction": direction,
            "note": note,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "width": meta["width"],
            "height": meta["height"],
            "mime": meta["mime"],
            "sha256": meta["sha256"],
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
    if not isinstance(furniture, list):
        return JSONResponse(
            status_code=400,
            content={"error": "furniture body must be a JSON array"},
        )
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


@app.post("/api/projects/{house}/schemes/{scheme_id}/confirm")
def confirm_project_scheme(house: str, scheme_id: str):
    try:
        return scheme_store.confirm_scheme(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.post("/api/projects/{house}/schemes/{scheme_id}/adjust")
def adjust_project_scheme(house: str, scheme_id: str, payload: dict = Body(...)):
    try:
        meta = scheme_store.adjust_scheme(DATA_DIR, house, scheme_id, payload)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return JSONResponse(status_code=201, content=meta)


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
    if not isinstance(furniture, list):
        return JSONResponse(
            status_code=400,
            content={"error": "furniture body must be a JSON array"},
        )
    try:
        scheme_store.write_furniture(DATA_DIR, house, scheme_id, furniture)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
    return {"ok": True}


# render 同为同步 CPU 纯函数: 用 def 让 FastAPI 派发到线程池, 不阻塞事件循环。
def _render_house_response(house: str, mode: str, scheme_id: str) -> Response | JSONResponse:
    if mode not in _RENDER_MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"mode must be one of {sorted(_RENDER_MODES)}, got {mode!r}"},
        )
    try:
        G, geo, furniture, _scheme_meta, scene = _load_scheme_scene(house, scheme_id)
        if mode == "plan2d":
            svg = axon.render_plan_2d(G, geo, furniture)          # out_path 省略 -> 仅返回字符串
            body = svg.encode("utf-8-sig")                        # 与 build.py 落盘一致 (带 BOM)
        else:
            geom = axon.geom_bundle(G, geo)
            svg = axon.render(geom, scene["axon_furniture"], mode=mode)  # 轴侧使用 scene 安全坐标
            body = svg.encode("utf-8")                            # 与 build.py 落盘一致 (无 BOM)
    except Exception as exc:  # noqa: BLE001 — 边界处显式回报, 不静默吞错
        if isinstance(exc, scheme_store.SchemeError):
            return _scheme_error_response(exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return Response(content=body, media_type="image/svg+xml")


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
def render_house(house: str, mode: str = "plan2d"):
    return _render_house_response(house, mode, "default")


@app.get("/api/projects/{house}/schemes/{scheme_id}/render")
def render_scheme_house(house: str, scheme_id: str, mode: str = "plan2d"):
    return _render_house_response(house, mode, scheme_id)


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
        provider = get_provider(_settings)
        # chat token 用量并入 /api/ai/status 计量 (审计: furnish 曾完全绕过预算/计量)。
        provider.on_usage = _budget.record_tokens
        result = furnish_service.generate_candidates(
            G,
            provider,
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


@app.get("/api/artifacts/{rel_path:path}")
def get_artifact(rel_path: str):
    """同源服务生成产物 (uuid 不可变, 可长缓存)。防穿越: resolve 越界 -> 404。"""
    target = _artifacts.resolve(rel_path)
    if target is None:
        return JSONResponse(status_code=404, content={"error": "artifact not found"})
    resp = FileResponse(str(target))
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.headers["X-Content-Type-Options"] = "nosniff"  # 禁 MIME 嗅探 (防内联脚本)
    return resp


@app.get("/api/uploads/{rel_path:path}")
def get_upload(rel_path: str):
    """同源服务用户上传图 (第6步空房照)。防穿越同 artifacts。"""
    target = _uploads.resolve(rel_path)
    if target is None:
        return JSONResponse(status_code=404, content={"error": "upload not found"})
    resp = FileResponse(str(target))
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


@app.post("/api/projects/{house}/uploads")
async def upload_image(house: str, file: UploadFile = File(...)):
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    ext = _UPLOAD_EXT.get((file.content_type or "").lower())
    if ext is None:
        return JSONResponse(
            status_code=415, content={"error": f"不支持的图片类型: {file.content_type}"}
        )
    # 读前先按声明大小早拒, 避免无界缓冲。
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "文件过大 (>15MB)"})
    # 有界读取: 至多 _MAX+1 字节, 超限即拒 (即便无 Content-Length 也不会无界缓冲)。
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not data:
        return JSONResponse(status_code=400, content={"error": "空文件"})
    if len(data) > _MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content={"error": "文件过大 (>15MB)"})
    try:
        # 归一化后落盘 (与照片端点同门禁); 同步落盘丢线程池, 不阻塞事件循环。
        data, _meta = await run_in_threadpool(imaging.normalize_photo, data)
        rel = await run_in_threadpool(
            _uploads.save, data, project_id=house, kind="empty", ext="jpg"
        )
    except AIError as exc:  # 非图像字节 -> 415 (归一化门禁)
        return JSONResponse(status_code=415, content={"error": str(exc)})
    except ValueError as exc:  # 段名/扩展名非法 -> 400
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except OSError as exc:  # 磁盘满/权限等落盘失败 -> 500 (不外泄栈)
        return JSONResponse(status_code=500, content={"error": f"保存失败: {exc}"})
    return {"ok": True, "path": rel, "url": f"/api/uploads/{rel}"}


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
        base_png = svg_to_png(svg, width=1536)                    # img2img 输入需位图
        # 1.5b 房内方位 + 审计 P0-6: 方案风格意向贯通到出图提示词 (无则回退默认现代轻奢)。
        style = (_scheme_meta.get("style_prompt") or "").strip() or None
        prompt = prompt_gen.generate(furniture, G, with_positions=True, style=style)
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
        try:
            res = provider.edit(prompt, [base_png], size="1536x1024", model=model)
        except Exception:
            _budget.release(house)  # 生成失败退预扣
            raise
        _budget.record_tokens(res.usage)
        rel = _artifacts.save_scoped(
            res.data, project_id=house, scope_id=scheme_id, kind="ai-render", ext="png"
        )
        record = {
            "id": rel.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "url": f"/api/artifacts/{rel}",
            "mode": "axon-photoreal",
            "scheme_id": scheme_id,
            "model": res.model,
            "with_positions": True,
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
def _real_render_prompt(photo: dict, furniture: list, G: dict) -> str:
    """实拍效果图提示词: 保第一张照片的真实房间结构, 按第二张轴测参考完成软装。"""
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
    direction_hint = (
        f"拍摄朝向为 {photo.get('direction')} 墙方向。" if photo.get("direction") else ""
    )
    return (
        "第一张图是房间的空房实拍照片, 第二张图是整套软装方案的轴测参考图。"
        "严格保持第一张照片的房间结构、门窗位置、墙面地面材质、透视与自然光照不变, "
        "按照第二张轴测参考图中对应房间的家具布局、款式与配色, 在照片中完成软装摆放。"
        "输出照片级真实感的室内实拍效果图, 不要改变相机角度。"
        + room_hint
        + direction_hint
    )


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
        svg = axon.render(geom, scene["axon_furniture"], mode="photo")
        axon_png = svg_to_png(svg, width=1536)
        prompt = _real_render_prompt(photo, furniture, G)
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
        try:
            # 多图: 空房照在前 (结构锚点), 轴测参考在后 (家具方案) — Phase 0 spike 验证的机制。
            res = provider.edit(prompt, [empty_png, axon_png], size="1536x1024", model=model)
        except Exception:
            _budget.release(house)  # 生成失败退预扣
            raise
        _budget.record_tokens(res.usage)
        rel_out = _artifacts.save_scoped(
            res.data, project_id=house, scope_id=scheme_id, kind="real-render", ext="png"
        )
        record = {
            "id": rel_out.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "url": f"/api/artifacts/{rel_out}",
            "mode": "real-photo",
            "scheme_id": scheme_id,
            "model": res.model,
            "photo_id": photo_id,
            "room_id": photo.get("room_id"),
            "usage": res.usage,
            "scene_manifest": manifest,
        }
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


@app.get("/api/projects/{house}/renders")
def list_renders(house: str):
    """AI 渲染历史 (最新在前)。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        return _list_default_renders(house)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)


@app.get("/api/projects/{house}/schemes/{scheme_id}/renders")
def list_scheme_renders(house: str, scheme_id: str):
    """AI 渲染历史 (最新在前)。"""
    if not _safe_project_id(house):
        return JSONResponse(status_code=400, content={"error": "id 非法"})
    try:
        return scheme_store.list_renders(DATA_DIR, house, scheme_id)
    except Exception as exc:  # noqa: BLE001
        return _scheme_error_response(exc)
