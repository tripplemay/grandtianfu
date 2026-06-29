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
from pathlib import Path

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from floorplan_core import axon, geometry  # 引擎库 (geometry/axon 单一真源)

from starlette.concurrency import run_in_threadpool

from aigc.artifacts import ArtifactStore  # AI 子系统 (Phase 1 基础设施)
from aigc.budget import BudgetGuard
from aigc.config import get_settings
from aigc.errors import AIError, BudgetExceeded, ProviderError
from aigc.jobs import JobManager

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
    return {"ok": True, "readonly": GEOM_READONLY}


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
        # 原子写 (新建项目无旧版, 故无 .bak); 字节同旧 open(w)+json.dump(indent=2/1)。
        _atomic_write_json(_geom_path(pid), G, indent=2)
        _atomic_write_json(_furniture_path(pid), [], indent=1)
    except Exception as exc:  # noqa: BLE001 — 落盘失败回滚半成品目录
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
        # 原子写 (覆盖前留 .bak); 字节同旧 open(w)+json.dump(indent=1), GET->原样 POST 回存 md5 不变。
        _atomic_write_json(path, furniture, indent=1)
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


# 上传图 (第6步: 空房实拍照). 仅图片类型; 存 UPLOADS_DIR/{house}/empty/.
_UPLOAD_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
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
        # 同步落盘丢线程池, 不阻塞事件循环 (本端点为 async, 与 render/derive 的同步派发同精神)。
        rel = await run_in_threadpool(
            _uploads.save, data, project_id=house, kind="empty", ext=ext
        )
    except ValueError as exc:  # 段名/扩展名非法 -> 400
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except OSError as exc:  # 磁盘满/权限等落盘失败 -> 500 (不外泄栈)
        return JSONResponse(status_code=500, content={"error": f"保存失败: {exc}"})
    return {"ok": True, "path": rel, "url": f"/api/uploads/{rel}"}
