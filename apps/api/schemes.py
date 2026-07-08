# -*- coding: utf-8 -*-
"""FurnitureScheme storage helpers.

Schemes are scoped to a concrete baseline version. Legacy root ``furniture.json``
remains the compatibility mirror for the ``default`` scheme, but the UI-facing
name is always "初始方案".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import baselines
from aigc.modes import RENDER_MODES

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# 进程内串行化多文件/读改写临界区 (单 uvicorn worker; 跨 worker 由 baselines.project_lock 兜底):
# _RENDERS_LOCK 保护 renders.json 的 list->insert->write; _PREFERRED_LOCK 保护首选唯一性多 meta 改写。
_RENDERS_LOCK = threading.Lock()
_PREFERRED_LOCK = threading.Lock()
# default 首写迁移 (mkdir+copy+meta 多步) 的进程内互斥; 幂等故锁内重查即可。
_ENSURE_DEFAULT_LOCK = threading.Lock()
_ALLOWED_SOURCES = {"legacy", "manual", "duplicate", "ai", "migrated"}
# 软装重构 Phase D: 砍掉 scheme 级 confirm。状态只剩 draft/archived; normalize 对遗留
# confirmed 自愈回落 draft (D-4), 迁移脚本 migrate_scheme_status 主动清盘 (D-1)。
_ALLOWED_STATUS = {"draft", "archived"}


class SchemeError(Exception):
    """Base scheme storage error."""


class SchemeNotFound(SchemeError):
    """Scheme or project was not found."""


class SchemeConflict(SchemeError):
    """Scheme already exists or cannot be modified."""


class SchemeValidationError(SchemeError):
    """Input payload is invalid."""


def safe_id(value: str) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def _project_dir(root: str | Path, project_id: str) -> Path:
    if not safe_id(project_id):
        raise SchemeValidationError("project_id 非法")
    path = Path(root) / project_id
    if not path.exists() or not path.is_dir():
        raise SchemeNotFound(f"project {project_id!r} not found")
    return path


def _root_furniture_path(project: Path) -> Path:
    return project / "furniture.json"


def _schemes_dir(project: Path) -> Path:
    return project / "schemes"


def _scheme_dir(project: Path, scheme_id: str) -> Path:
    if not safe_id(scheme_id):
        raise SchemeValidationError("scheme_id 非法")
    return _schemes_dir(project) / scheme_id


def _meta_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "meta.json"


def _furniture_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "furniture.json"


def _renders_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "renders.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write_json(path: Path, obj, *, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    # fsync 补齐 (审计 P2 legacy 收口): 与 baselines.atomic_write_json 同等耐久 ——
    # 掉电不再产生"目录里 renders.json 有记录但内容半截"的静默截断。序列化字节不变。
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=indent))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _load_furniture_file(path: Path) -> list:
    return _coerce_list_payload(_read_json(path, []), what="furniture.json")


def _current_baseline_id(root: str | Path, project_id: str) -> str:
    try:
        project_meta = baselines.get_project(root, project_id)
    except baselines.BaselineError as exc:
        raise SchemeError(str(exc)) from exc
    value = project_meta.get("current_baseline_version_id")
    if not value:
        raise SchemeConflict("当前没有已确认户型，禁止创建方案")
    return str(value)


def _baseline_status(root: str | Path, project_id: str, baseline_id: str) -> str:
    try:
        meta = baselines.get_baseline(root, project_id, baseline_id)
    except baselines.BaselineError as exc:
        raise SchemeError(str(exc)) from exc
    return str(meta.get("status") or "")


def _default_meta(*, virtual: bool, baseline_version_id: str = "v1") -> dict:
    ts = None if virtual else _now()
    return {
        "id": "default",
        "name": "初始方案",
        "source": "legacy",
        "style_prompt": "",
        "base_scheme_id": None,
        "status": "draft",
        "baseline_version_id": baseline_version_id,
        "preferred": False,
        "archived_at": None,
        "created_at": ts,
        "updated_at": ts,
    }


def _normalize_meta(project: Path, scheme_id: str, meta: dict | None) -> dict:
    data = dict(meta or {})
    data.setdefault("id", scheme_id)
    if scheme_id == "default":
        data["name"] = "初始方案"
        data.setdefault("source", "legacy")
        data.setdefault("status", "draft")
    else:
        data.setdefault("name", scheme_id)
        data.setdefault("source", "manual")
    # 状态自愈 (Phase D / D-4): 遗留 confirmed(含 default —— 旧 UI 允许确认初始方案)一律回落
    # draft, 保证写门永不见 confirmed。两分支统一, 修复 default 分支 setdefault 不自愈的洞。
    if data.get("status") not in _ALLOWED_STATUS:
        data["status"] = "draft"
    if data.get("source") not in _ALLOWED_SOURCES:
        data["source"] = "manual"
    data.setdefault("style_prompt", "")
    data.setdefault("base_scheme_id", None)
    data.setdefault("baseline_version_id", _current_baseline_id(project.parent, project.name))
    data.setdefault("preferred", False)
    data.setdefault("archived_at", None)
    data.setdefault("created_at", None)
    data.setdefault("updated_at", None)
    # 单位契约自描述 (审计 P1-6): furniture 条目 dx/dy/w/h/r=px(1px=10mm), z=mm。
    data.setdefault("units", {"xy": "px", "z": "mm", "mm_per_px": 10})
    return data


def _load_meta(project: Path, scheme_id: str) -> dict:
    if scheme_id == "default" and not _meta_path(project, "default").exists():
        return _default_meta(
            virtual=True,
            baseline_version_id=_current_baseline_id(project.parent, project.name),
        )
    meta_path = _meta_path(project, scheme_id)
    if not meta_path.exists():
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
    data = _read_json(meta_path, None)
    if not isinstance(data, dict):
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
    return _normalize_meta(project, scheme_id, data)


def _write_meta(project: Path, scheme_id: str, meta: dict) -> None:
    _atomic_write_json(_meta_path(project, scheme_id), _normalize_meta(project, scheme_id, meta), indent=2)


def _ensure_default(project: Path) -> None:
    with _ENSURE_DEFAULT_LOCK:
        _ensure_default_locked(project)


def _ensure_default_locked(project: Path) -> None:
    default_dir = _scheme_dir(project, "default")
    if default_dir.exists():
        meta = _load_meta(project, "default")
        changed = (
            meta.get("name") != "初始方案"
            or "baseline_version_id" not in meta
            or "preferred" not in meta
            or "archived_at" not in meta
        )
        if changed:
            _write_meta(project, "default", meta)
        return
    root_furniture = _root_furniture_path(project)
    if not root_furniture.exists():
        raise SchemeNotFound("root furniture.json not found")
    default_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root_furniture, default_dir / "furniture.json")
    _write_meta(
        project,
        "default",
        _default_meta(
            virtual=False,
            baseline_version_id=_current_baseline_id(project.parent, project.name),
        ),
    )
    if not (default_dir / "renders.json").exists():
        _atomic_write_json(default_dir / "renders.json", [], indent=None)


def _require_scheme(project: Path, scheme_id: str) -> None:
    if scheme_id == "default":
        root = _root_furniture_path(project)
        if not root.exists() and not _furniture_path(project, "default").exists():
            raise SchemeNotFound("default furniture not found")
        return
    if not _scheme_dir(project, scheme_id).is_dir():
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")


def _assert_scheme_writable(
    root: str | Path,
    project_id: str,
    meta: dict,
) -> None:
    baseline_id = str(meta.get("baseline_version_id") or "")
    if not baseline_id:
        raise SchemeConflict("scheme missing baseline_version_id")
    current_id = _current_baseline_id(root, project_id)
    if baseline_id != current_id:
        raise SchemeConflict("方案对应户型已进入历史，禁止写入")
    if _baseline_status(root, project_id, baseline_id) != "confirmed":
        raise SchemeConflict("方案绑定的户型版本不是当前已确认版本")
    status = meta.get("status") or "draft"
    if status == "archived":
        raise SchemeConflict("已归档方案禁止写入")
    if status not in _ALLOWED_STATUS:
        raise SchemeConflict("方案状态非法")


def _summary(project: Path, scheme_id: str) -> dict:
    meta = _load_meta(project, scheme_id)
    items = len(read_furniture(project.parent, project.name, scheme_id))
    render_items = list_renders(project.parent, project.name, scheme_id)
    return {
        "id": meta.get("id", scheme_id),
        "name": meta.get("name") or scheme_id,
        "source": meta.get("source") or "manual",
        "style_prompt": meta.get("style_prompt") or "",
        "status": meta.get("status") or "draft",
        "baseline_version_id": meta.get("baseline_version_id"),
        "preferred": bool(meta.get("preferred")),
        "archived_at": meta.get("archived_at"),
        "items": items,
        "renders": len(render_items),
        "latest_render_url": render_items[0].get("url") if render_items and isinstance(render_items[0], dict) else None,
        "latest_render_thumb_url": render_items[0].get("thumb_url") if render_items and isinstance(render_items[0], dict) else None,
        "updated_at": meta.get("updated_at"),
    }


def list_schemes(
    root: str | Path,
    project_id: str,
    *,
    baseline_version_id: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    project = _project_dir(root, project_id)
    # 尚无已确认户型的新项目: 不可能有任何方案, 读列表返回空 (不套 create 门, 否则 409 会
    # 毒化工作流上下文, 使首个户型草稿只读、无法确认)。审计 A / P4。
    try:
        current = _current_baseline_id(root, project_id)
    except SchemeConflict:
        return []
    target_baseline = baseline_version_id or current
    schemes_root = _schemes_dir(project)
    if not schemes_root.exists():
        items = [_summary(project, "default")]
    else:
        items: list[dict] = []
        for child in sorted(schemes_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                items.append(_summary(project, child.name))
            except SchemeNotFound:
                continue
        if not any(item["id"] == "default" for item in items):
            items.insert(0, _summary(project, "default"))
    return [
        item
        for item in items
        if item.get("baseline_version_id") == target_baseline
        and (include_archived or item.get("status") != "archived")
    ]


def get_scheme(root: str | Path, project_id: str, scheme_id: str) -> dict:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    return _load_meta(project, scheme_id)


def create_scheme(root: str | Path, project_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
    scheme_id = payload.get("id")
    if not safe_id(scheme_id):
        raise SchemeValidationError("scheme id 非法")
    if scheme_id == "default":
        raise SchemeConflict("default scheme already exists")
    source = payload.get("source", "manual")
    if source not in _ALLOWED_SOURCES - {"legacy", "migrated"}:
        raise SchemeValidationError("source 非法")
    furniture = payload.get("furniture", [])
    if not isinstance(furniture, list):
        raise SchemeValidationError("furniture must be an array")
    target = _scheme_dir(project, scheme_id)
    if target.exists():
        raise SchemeConflict(f"scheme {scheme_id!r} already exists")
    _ensure_default(project)
    baseline_id = payload.get("baseline_version_id") or _current_baseline_id(root, project_id)
    if baseline_id != _current_baseline_id(root, project_id):
        raise SchemeConflict("只能在当前户型版本下创建方案")
    if _baseline_status(root, project_id, baseline_id) != "confirmed":
        raise SchemeConflict("当前没有已确认户型，禁止创建方案")
    # 软装重构 Phase B: 手建方案(未带家具)从当前基线的标准布局拷种子, 而非空白 ——
    # 方案 = 锁定布局的风格副本, 用户在此基础上换件/调风格。AI/duplicate 走各自路径不受此影响。
    if not furniture and source == "manual":
        try:
            furniture = baselines.read_baseline_furniture(root, project_id, baseline_id)
        except baselines.BaselineError:
            furniture = []
    now = _now()
    meta = {
        "id": scheme_id,
        "name": payload.get("name") or scheme_id,
        "source": source,
        "style_prompt": payload.get("style_prompt") or "",
        "base_scheme_id": payload.get("base_scheme_id"),
        "status": payload.get("status") if payload.get("status") in _ALLOWED_STATUS else "draft",
        "baseline_version_id": baseline_id,
        "preferred": False,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    # 生成溯源可选字段 (审计 P2-6): AI 用的 LLM 模型 / 布局与校验告警 / 目录修订号。
    for key in ("model", "furnish_warnings", "catalog_rev"):
        if payload.get(key) is not None:
            meta[key] = payload[key]
    target.mkdir(parents=True, exist_ok=False)
    _write_meta(project, scheme_id, meta)
    _atomic_write_json(target / "furniture.json", furniture, indent=1)
    _atomic_write_json(target / "renders.json", [], indent=None)
    return _load_meta(project, scheme_id)


def duplicate_scheme(root: str | Path, project_id: str, source_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
    source_meta = get_scheme(root, project_id, source_id)
    _assert_scheme_writable(root, project_id, source_meta)
    target_id = payload.get("id")
    if not safe_id(target_id) or target_id == "default":
        raise SchemeValidationError("target scheme id 非法")
    target = _scheme_dir(project, target_id)
    if target.exists():
        raise SchemeConflict(f"scheme {target_id!r} already exists")
    furniture = read_furniture(root, project_id, source_id)
    _ensure_default(project)
    now = _now()
    meta = {
        "id": target_id,
        "name": payload.get("name") or f"{source_meta.get('name') or source_id} 副本",
        "source": "duplicate",
        "style_prompt": source_meta.get("style_prompt") or "",
        "base_scheme_id": source_id,
        "status": "draft",
        "baseline_version_id": source_meta.get("baseline_version_id"),
        "preferred": False,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    target.mkdir(parents=True, exist_ok=False)
    _write_meta(project, target_id, meta)
    _atomic_write_json(target / "furniture.json", furniture, indent=1)
    _atomic_write_json(target / "renders.json", [], indent=None)
    return _load_meta(project, target_id)


def patch_scheme(root: str | Path, project_id: str, scheme_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
    _ensure_default(project)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
    if "name" in payload:
        if not isinstance(payload["name"], str) or not payload["name"].strip():
            raise SchemeValidationError("name must be a non-empty string")
        meta["name"] = payload["name"].strip()
    # Phase D (D-3): patch 不再改 status —— 归档/恢复各有独立端点, status 只剩 draft/archived。
    meta["updated_at"] = _now()
    _write_meta(project, scheme_id, meta)
    return _load_meta(project, scheme_id)


# Phase D (D-2): confirm_scheme / adjust_scheme 已移除 —— 方案不再有"确认锁"; 需要副本走
# duplicate_scheme(等价语义, 可对任意可写方案创建 draft 副本)。


def restore_scheme(root: str | Path, project_id: str, scheme_id: str) -> dict:
    """恢复已归档方案 (Phase D / D-5): archived -> draft。归档=可逆暂存, 非黑洞。

    绕过写门的"已归档禁写"(本操作正是要解归档), 但仍要求方案绑定的户型是当前已确认版本
    (不能把方案恢复到历史户型上)。"""
    project = _project_dir(root, project_id)
    meta = _load_meta(project, scheme_id)
    if meta.get("status") != "archived":
        raise SchemeConflict("只能恢复已归档方案")
    baseline_id = str(meta.get("baseline_version_id") or "")
    if baseline_id != _current_baseline_id(root, project_id):
        raise SchemeConflict("方案对应户型已进入历史，无法恢复")
    if _baseline_status(root, project_id, baseline_id) != "confirmed":
        raise SchemeConflict("方案绑定的户型版本不是当前已确认版本")
    meta["status"] = "draft"
    meta["archived_at"] = None
    meta["updated_at"] = _now()
    _write_meta(project, scheme_id, meta)
    return _load_meta(project, scheme_id)


def migrate_scheme_status(root: str | Path) -> dict:
    """D-1 一次性迁移: 遍历所有项目所有方案, 把磁盘上遗留的 status=confirmed 改写为 draft。

    幂等(仅动 confirmed 件, 只改 status 字段, 保留其余); 供 scripts/migrate_scheme_status.py
    在 VPS 上执行主动清盘。读路径的 normalize 亦会自愈遗留 confirmed (D-4), 本脚本是显式清理。"""
    root = Path(root)
    changed: list[str] = []
    if not root.exists():
        return {"changed": [], "count": 0}
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        schemes_dir = project / "schemes"
        if not schemes_dir.is_dir():
            continue
        for sdir in sorted(s for s in schemes_dir.iterdir() if s.is_dir()):
            meta_path = sdir / "meta.json"
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except (ValueError, OSError):
                continue
            if meta.get("status") == "confirmed":
                meta["status"] = "draft"
                meta["updated_at"] = _now()
                _atomic_write_json(meta_path, meta, indent=2)
                changed.append(f"{project.name}/{sdir.name}")
    return {"changed": changed, "count": len(changed)}


def archive_scheme(root: str | Path, project_id: str, scheme_id: str) -> dict:
    if scheme_id == "default":
        raise SchemeConflict("初始方案不能归档")
    project = _project_dir(root, project_id)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
    meta["status"] = "archived"
    meta["preferred"] = False
    meta["archived_at"] = _now()
    meta["updated_at"] = meta["archived_at"]
    _write_meta(project, scheme_id, meta)
    return _load_meta(project, scheme_id)


def set_preferred(root: str | Path, project_id: str, scheme_id: str) -> dict:
    project = _project_dir(root, project_id)
    # 首选唯一性跨多个 meta.json, 持进程锁保证并发 set-preferred 不交错出 0/2 个首选。
    with _PREFERRED_LOCK:
        target_meta = _load_meta(project, scheme_id)
        _assert_scheme_writable(root, project_id, target_meta)
        if target_meta.get("status") == "archived":
            raise SchemeConflict("已归档方案不能设为首选")
        baseline_id = target_meta.get("baseline_version_id")
        now = _now()
        for item in list_schemes(
            root,
            project_id,
            baseline_version_id=str(baseline_id),
            include_archived=True,
        ):
            sid = item["id"]
            meta = _load_meta(project, sid)
            should_prefer = sid == scheme_id
            if bool(meta.get("preferred")) != should_prefer:
                meta["preferred"] = should_prefer
                meta["updated_at"] = now
                _write_meta(project, sid, meta)
        return _load_meta(project, scheme_id)


def migrate_scheme(root: str | Path, project_id: str, scheme_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
    source_meta = get_scheme(root, project_id, scheme_id)
    target_baseline = payload.get("target_baseline_version_id") or _current_baseline_id(root, project_id)
    if target_baseline != _current_baseline_id(root, project_id):
        raise SchemeConflict("目标户型必须是当前户型版本")
    if _baseline_status(root, project_id, target_baseline) != "confirmed":
        raise SchemeConflict("目标户型必须是当前已确认版本")
    if source_meta.get("baseline_version_id") == target_baseline:
        raise SchemeConflict("源方案已经属于目标户型版本")
    target_id = payload.get("id")
    if not safe_id(target_id) or target_id == "default":
        raise SchemeValidationError("target scheme id 非法")
    target = _scheme_dir(project, target_id)
    if target.exists():
        raise SchemeConflict(f"scheme {target_id!r} already exists")
    furniture = read_furniture(root, project_id, scheme_id)
    warnings = _migration_warnings(root, project_id, target_baseline, furniture)
    now = _now()
    meta = {
        "id": target_id,
        "name": payload.get("name") or f"{source_meta.get('name') or scheme_id} - {target_baseline}",
        "source": "migrated",
        "style_prompt": source_meta.get("style_prompt") or "",
        "base_scheme_id": scheme_id,
        "status": "draft",
        "baseline_version_id": target_baseline,
        "preferred": False,
        "archived_at": None,
        "migration_warnings": warnings,
        "created_at": now,
        "updated_at": now,
    }
    target.mkdir(parents=True, exist_ok=False)
    _write_meta(project, target_id, meta)
    _atomic_write_json(target / "furniture.json", furniture, indent=1)
    _atomic_write_json(target / "renders.json", [], indent=None)
    return _load_meta(project, target_id)


def _migration_warnings(
    root: str | Path,
    project_id: str,
    target_baseline: str,
    furniture: list,
) -> list[str]:
    warnings: list[str] = []
    try:
        target_geometry = baselines.read_baseline_geometry(root, project_id, target_baseline)
    except baselines.BaselineError as exc:
        return [f"无法读取目标户型校验家具映射: {exc}"]
    rooms = target_geometry.get("rooms", []) if isinstance(target_geometry, dict) else []
    room_map = {room.get("id"): room for room in rooms if isinstance(room, dict)}
    room_ids = set(room_map.keys())
    for idx, item in enumerate(furniture):
        if not isinstance(item, dict):
            warnings.append(f"家具 #{idx + 1} 不是对象，已原样保留")
            continue
        room_id = item.get("room_id")
        if room_id and room_id not in room_ids:
            warnings.append(f"家具 #{idx + 1} 引用不存在房间 {room_id}，已原样保留")
            continue
        room = room_map.get(room_id)
        rect = room.get("rect") if isinstance(room, dict) else None
        if isinstance(rect, list) and len(rect) == 4:
            x, y, w, h = rect
            if "dcx" in item and "dcy" in item:
                cx = item.get("dcx")
                cy = item.get("dcy")
                if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                    if cx < 0 or cy < 0 or cx > w or cy > h:
                        warnings.append(f"家具 #{idx + 1} 中心点超出房间 {room_id}，已原样保留")
            elif "dx" in item and "dy" in item:
                dx = item.get("dx")
                dy = item.get("dy")
                fw = item.get("w", 0)
                fh = item.get("h", 0)
                if all(isinstance(v, (int, float)) for v in (dx, dy, fw, fh)):
                    if dx < 0 or dy < 0 or dx + fw > w or dy + fh > h:
                        warnings.append(f"家具 #{idx + 1} 边界超出房间 {room_id}，已原样保留")
    return warnings


def delete_scheme(root: str | Path, project_id: str, scheme_id: str) -> dict:
    project = _project_dir(root, project_id)
    if scheme_id == "default":
        raise SchemeError("default scheme cannot be deleted")
    target = _scheme_dir(project, scheme_id)
    if not target.exists() or not target.is_dir():
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
    trash = _schemes_dir(project) / ".trash"
    trash.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    dest = trash / f"{scheme_id}-{ts}"
    shutil.move(str(target), str(dest))
    return {"ok": True, "trashed": dest.name}


def read_furniture(root: str | Path, project_id: str, scheme_id: str = "default") -> list:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    if scheme_id == "default":
        scheme_path = _furniture_path(project, "default")
        if scheme_path.exists():
            return _load_furniture_file(scheme_path)
        return _load_furniture_file(_root_furniture_path(project))
    return _load_furniture_file(_furniture_path(project, scheme_id))


def write_furniture(
    root: str | Path, project_id: str, scheme_id: str, furniture: list
) -> dict:
    if not isinstance(furniture, list):
        raise SchemeValidationError("furniture must be an array")
    project = _project_dir(root, project_id)
    _ensure_default(project)
    _require_scheme(project, scheme_id)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
    path = _furniture_path(project, scheme_id)
    _atomic_write_json(path, furniture, indent=1)
    if scheme_id == "default":
        _atomic_write_json(_root_furniture_path(project), furniture, indent=1)
    meta["updated_at"] = _now()
    _write_meta(project, scheme_id, meta)
    return {"ok": True}


def _coerce_list_payload(data, *, what: str) -> list:
    """裸数组为准; 兼容未来 {"items": [...]} 包裹; 其它形状显式抛错。

    审计 P2-1: 旧代码把未知格式静默读成 [] —— 家具/历史"消失"比报错难排查得多。"""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise SchemeValidationError(f"{what} 文件格式不受支持 (需数组或 {{items: []}}), 请升级服务")


def list_renders(root: str | Path, project_id: str, scheme_id: str = "default") -> list:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    return _coerce_list_payload(
        _read_json(_renders_path(project, scheme_id), []), what="renders.json"
    )


def append_render(
    root: str | Path, project_id: str, scheme_id: str, record: dict, *, cap: int = 200
) -> None:
    project = _project_dir(root, project_id)
    _ensure_default(project)
    _require_scheme(project, scheme_id)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
    mode = record.get("mode")
    if mode and mode not in RENDER_MODES:
        raise SchemeValidationError(f"未知渲染 mode: {mode!r} (allowed: {sorted(RENDER_MODES)})")
    # 读-改-写持锁: 并发出图 (JobManager 双 worker) 同方案 append 不互相覆盖丢历史。
    with _RENDERS_LOCK:
        items = list_renders(root, project_id, scheme_id)
        items.insert(0, record)
        del items[cap:]
        _atomic_write_json(_renders_path(project, scheme_id), items, indent=None)


def remove_render(
    root: str | Path, project_id: str, scheme_id: str, render_id: str
) -> dict | None:
    """从方案级 renders.json 摘除一条效果图记录 (按 id, 缺 id 回退 url), 返回被删记录。

    只动 DATA_DIR 的记录账本 (物理图片文件由调用方 unlink, ARTIFACTS_DIR 属另一层);
    复用 _RENDERS_LOCK 与 append 同一把锁, 防并发 append 覆盖。未命中返回 None。
    允许删已确认/归档方案的历史效果图 (清理而非生成, 不走 _assert_scheme_writable)。
    """
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    with _RENDERS_LOCK:
        items = list_renders(root, project_id, scheme_id)
        removed: dict | None = None
        kept: list = []
        for rec in items:
            if (
                removed is None
                and isinstance(rec, dict)
                and (rec.get("id") == render_id or rec.get("url") == render_id)
            ):
                removed = rec
                continue
            kept.append(rec)
        if removed is not None:
            _atomic_write_json(_renders_path(project, scheme_id), kept, indent=None)
        return removed


def assert_can_generate_render(root: str | Path, project_id: str, scheme_id: str) -> None:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)


def assert_can_create_from_scheme(root: str | Path, project_id: str, scheme_id: str) -> None:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    meta = _load_meta(project, scheme_id)
    _assert_scheme_writable(root, project_id, meta)
