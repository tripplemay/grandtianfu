# -*- coding: utf-8 -*-
"""Project baseline storage and migration helpers.

Stage 0 intentionally keeps this module independent from the active API routes:
it provides the file model, project-level lock, and idempotent migration/dry-run
that later stages can use without changing existing production read/write paths.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import time
from contextlib import contextmanager
from contextlib import nullcontext
from pathlib import Path
from typing import Iterator

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

BASELINE_STATUSES = {"draft", "confirmed", "superseded"}
SCHEME_STATUSES = {"draft", "confirmed", "archived"}


class BaselineError(Exception):
    """Base baseline storage error."""


class BaselineNotFound(BaselineError):
    """Project or baseline was not found."""


class BaselineConflict(BaselineError):
    """The requested operation conflicts with current project state."""


class BaselineValidationError(BaselineError):
    """Input payload or persisted metadata is invalid."""


def safe_id(value: str) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _project_dir(root: str | Path, project_id: str) -> Path:
    if not safe_id(project_id):
        raise BaselineValidationError("project_id 非法")
    path = Path(root) / project_id
    if not path.exists() or not path.is_dir():
        raise BaselineNotFound(f"project {project_id!r} not found")
    return path


def _project_json_path(project: Path) -> Path:
    return project / "project.json"


def _root_geometry_path(project: Path) -> Path:
    return project / "geometry.json"


def _root_furniture_path(project: Path) -> Path:
    return project / "furniture.json"


def _baselines_dir(project: Path) -> Path:
    return project / "baselines"


def _baseline_dir(project: Path, version_id: str) -> Path:
    if not safe_id(version_id):
        raise BaselineValidationError("baseline version id 非法")
    return _baselines_dir(project) / version_id


def _baseline_meta_path(project: Path, version_id: str) -> Path:
    return _baseline_dir(project, version_id) / "meta.json"


def _baseline_geometry_path(project: Path, version_id: str) -> Path:
    return _baseline_dir(project, version_id) / "geometry.json"


def _baseline_furniture_path(project: Path, version_id: str) -> Path:
    # 家具下沉基线 (CP软装重构 Phase A): 与户型同版本锁定的标准布局家具。
    return _baseline_dir(project, version_id) / "furniture.json"


def _baseline_validation_path(project: Path, version_id: str) -> Path:
    return _baseline_dir(project, version_id) / "validation.json"


def _schemes_dir(project: Path) -> Path:
    return project / "schemes"


def _scheme_dir(project: Path, scheme_id: str) -> Path:
    if not safe_id(scheme_id):
        raise BaselineValidationError("scheme_id 非法")
    return _schemes_dir(project) / scheme_id


def _scheme_meta_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "meta.json"


def _scheme_furniture_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "furniture.json"


def _scheme_renders_path(project: Path, scheme_id: str) -> Path:
    return _scheme_dir(project, scheme_id) / "renders.json"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def atomic_write_json(path: Path, obj, *, indent: int | None = 2) -> None:
    """Atomically write JSON using same bytes as json.dumps(..., ensure_ascii=False).

    The write pattern is same-directory temp file + fsync + os.replace. A ``.bak``
    copy is kept only for overwrites, matching the existing API storage style.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, indent=indent).encode("utf-8")
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    if path.exists():
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _fsync_dir(path: Path) -> None:
    try:
        dir_fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


@contextmanager
def project_lock(
    root: str | Path,
    project_id: str,
    *,
    timeout_s: float = 10.0,
    poll_s: float = 0.05,
) -> Iterator[Path]:
    """Acquire an exclusive project-level filesystem lock (``fcntl.flock`` 咨询锁)。

    锁与进程绑定: 持锁进程退出/崩溃 (kill -9) 时内核自动释放, 故无需 mtime 陈旧检测——
    消除了旧实现 "stat(mtime) + unlink 破锁" 的 TOCTOU 竞态 (读 mtime 与 unlink 之间,
    另一 worker 可能已重建新锁, 旧代码会误删他人新鲜锁)。

    ``{project}/.project.lock`` 作持久锁句柄 (不 unlink, 复用); 同主机多 worker 据此
    串行化临界区。POSIX-only (Linux 生产 + macOS dev); flock 按 open file description,
    同进程另开 fd 也会竞争, 序列化语义与旧 O_EXCL 一致。
    """
    project = _project_dir(root, project_id)
    lock_path = project / ".project.lock"
    deadline = time.monotonic() + timeout_s
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise BaselineConflict(f"project {project_id!r} is locked") from exc
                time.sleep(poll_s)
        # 记录持锁者 (仅供 ops 排查, 不参与锁语义)。
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"pid={os.getpid()} acquired_at={_now()}\n".encode("utf-8"))
            os.fsync(fd)
        except OSError:
            pass
        yield lock_path
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _project_name_from_geometry(project: Path, project_id: str) -> str:
    data = _read_json(_root_geometry_path(project))
    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("name"), str) and meta["name"].strip():
            return meta["name"].strip()
    return project_id


def _existing_version_ids(project: Path) -> list[str]:
    root = _baselines_dir(project)
    if not root.exists():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and safe_id(child.name)
    )


def _next_version_number(version_ids: list[str]) -> int:
    highest = 0
    for vid in version_ids:
        if vid.startswith("v") and vid[1:].isdigit():
            highest = max(highest, int(vid[1:]))
    return max(highest + 1, 2)


def _validation_payload(project: Path, version_id: str) -> dict:
    geometry_path = _baseline_geometry_path(project, version_id)
    if not geometry_path.exists():
        geometry_path = _root_geometry_path(project)
    payload = {
        "version_id": version_id,
        "validated_at": _now(),
        "issues": [],
    }
    data = _read_json(geometry_path)
    if not isinstance(data, dict):
        payload["issues"].append({"level": "ERROR", "message": "geometry.json 不是对象"})
        return payload
    try:
        from floorplan_core import geometry as geometry_core

        payload["issues"] = [
            {"level": level, "message": message}
            for level, message in geometry_core.validate(data)
        ]
    except Exception as exc:  # noqa: BLE001 - validation failure is recorded, not fatal.
        payload["issues"] = [{"level": "ERROR", "message": f"校验失败: {exc}"}]
    return payload


def _record(report: dict, action: str, path: Path, **details) -> None:
    item = {
        "action": action,
        "path": str(path),
    }
    item.update(details)
    report["operations"].append(item)


def _write_json_if_changed(
    report: dict,
    path: Path,
    payload: dict | list,
    *,
    dry_run: bool,
    indent: int | None = 2,
    action: str,
) -> None:
    current = _read_json(path)
    if current == payload:
        return
    _record(report, action if current is None else "update", path)
    if not dry_run:
        atomic_write_json(path, payload, indent=indent)


def _write_json_if_missing(
    report: dict,
    path: Path,
    payload: dict | list,
    *,
    dry_run: bool,
    indent: int | None = 2,
    action: str,
) -> None:
    if path.exists():
        return
    _record(report, action, path)
    if not dry_run:
        atomic_write_json(path, payload, indent=indent)


def _copy_bytes_if_missing(
    report: dict,
    src: Path,
    dest: Path,
    *,
    dry_run: bool,
    action: str,
) -> None:
    if dest.exists():
        return
    if not src.exists():
        report["warnings"].append(f"missing source file: {src}")
        return
    _record(report, action, dest, source=str(src))
    if not dry_run:
        _atomic_write_bytes(dest, src.read_bytes())


def _merge_project_meta(project: Path, project_id: str, now: str) -> dict:
    existing = _read_json(_project_json_path(project))
    if not isinstance(existing, dict):
        existing = {}
    version_ids = _existing_version_ids(project)
    meta = dict(existing)
    meta.setdefault("id", project_id)
    meta.setdefault("name", _project_name_from_geometry(project, project_id))
    meta.setdefault("current_baseline_version_id", "v1")
    meta.setdefault("next_baseline_version", _next_version_number(version_ids or ["v1"]))
    meta.setdefault("created_at", now)
    meta["updated_at"] = meta.get("updated_at") or now
    return meta


def _merge_baseline_v1_meta(project: Path, now: str) -> dict:
    existing = _read_json(_baseline_meta_path(project, "v1"))
    if not isinstance(existing, dict):
        existing = {}
    meta = dict(existing)
    meta.setdefault("id", "v1")
    meta.setdefault("status", "confirmed")
    meta.setdefault("source_version_id", None)
    meta.setdefault("created_at", now)
    meta.setdefault("confirmed_at", now)
    meta.setdefault("superseded_at", None)
    return meta


def _synthetic_project_meta(project: Path, project_id: str) -> dict:
    version_ids = _existing_version_ids(project) or ["v1"]
    return {
        "id": project_id,
        "name": _project_name_from_geometry(project, project_id),
        "current_baseline_version_id": "v1",
        "next_baseline_version": _next_version_number(version_ids),
        "created_at": None,
        "updated_at": None,
    }


def _load_project_meta(project: Path, project_id: str) -> dict:
    data = _read_json(_project_json_path(project))
    if not isinstance(data, dict):
        return _synthetic_project_meta(project, project_id)
    meta = dict(data)
    meta.setdefault("id", project_id)
    meta.setdefault("name", _project_name_from_geometry(project, project_id))
    meta.setdefault("current_baseline_version_id", "v1")
    meta.setdefault("next_baseline_version", _next_version_number(_existing_version_ids(project) or ["v1"]))
    meta.setdefault("created_at", None)
    meta.setdefault("updated_at", None)
    return meta


def _synthetic_baseline_v1_meta() -> dict:
    return {
        "id": "v1",
        "status": "confirmed",
        "source_version_id": None,
        "created_at": None,
        "confirmed_at": None,
        "superseded_at": None,
    }


def _load_baseline_meta(project: Path, version_id: str) -> dict:
    if not safe_id(version_id):
        raise BaselineValidationError("baseline version id 非法")
    data = _read_json(_baseline_meta_path(project, version_id))
    if isinstance(data, dict):
        meta = dict(data)
        meta.setdefault("id", version_id)
        if meta.get("status") not in BASELINE_STATUSES:
            raise BaselineValidationError(f"baseline {version_id!r} status 非法")
        validation = _read_json(_baseline_validation_path(project, version_id))
        if isinstance(validation, dict):
            meta["validation_issues"] = validation.get("issues", [])
        return meta
    if version_id == "v1" and _root_geometry_path(project).exists():
        return _synthetic_baseline_v1_meta()
    raise BaselineNotFound(f"baseline {version_id!r} not found")


def _persist_baseline_meta(project: Path, version_id: str, meta: dict) -> None:
    clean = dict(meta)
    clean.pop("validation_issues", None)
    atomic_write_json(_baseline_meta_path(project, version_id), clean, indent=2)


def _baseline_sort_key(meta: dict) -> tuple[int, str]:
    version_id = str(meta.get("id") or "")
    if version_id.startswith("v") and version_id[1:].isdigit():
        return (int(version_id[1:]), version_id)
    return (10**9, version_id)


def get_project(root: str | Path, project_id: str) -> dict:
    project = _project_dir(root, project_id)
    return _load_project_meta(project, project_id)


def list_baselines(root: str | Path, project_id: str) -> list[dict]:
    project = _project_dir(root, project_id)
    version_ids = _existing_version_ids(project)
    if not version_ids and _root_geometry_path(project).exists():
        version_ids = ["v1"]
    metas = [_load_baseline_meta(project, version_id) for version_id in version_ids]
    return sorted(metas, key=_baseline_sort_key)


def get_baseline(root: str | Path, project_id: str, version_id: str) -> dict:
    project = _project_dir(root, project_id)
    return _load_baseline_meta(project, version_id)


def read_baseline_geometry(root: str | Path, project_id: str, version_id: str) -> dict:
    project = _project_dir(root, project_id)
    _load_baseline_meta(project, version_id)
    path = _baseline_geometry_path(project, version_id)
    if version_id == "v1" and not path.exists():
        path = _root_geometry_path(project)
    data = _read_json(path)
    if not isinstance(data, dict):
        raise BaselineNotFound(f"baseline {version_id!r} geometry not found")
    return data


def read_baseline_furniture(root: str | Path, project_id: str, version_id: str) -> list:
    """基线标准布局家具 (Phase A)。furniture.json 缺失 (v1 未物化, 或 Phase A 之前创建的旧
    户型版本从未落家具) 一律回退根 furniture.json (= 初始方案家具) —— 基线版本恒为派生副本,
    未物化即取初始布局, 不应是空。件被编辑保存后自有 furniture.json, 不再回退。"""
    project = _project_dir(root, project_id)
    _load_baseline_meta(project, version_id)
    path = _baseline_furniture_path(project, version_id)
    if not path.exists():
        path = _root_furniture_path(project)
    data = _read_json(path)
    if data is None:
        return []
    if not isinstance(data, list):
        raise BaselineValidationError(f"baseline {version_id!r} furniture 格式非数组")
    return data


def _ensure_project_structure(root: str | Path, project_id: str) -> None:
    project = _project_dir(root, project_id)
    if (
        _project_json_path(project).exists()
        and _baseline_meta_path(project, "v1").exists()
        and _baseline_geometry_path(project, "v1").exists()
    ):
        return
    migrate_project(root, project_id, dry_run=False)


def _next_version_id(project_meta: dict) -> str:
    try:
        number = int(project_meta.get("next_baseline_version", 2))
    except (TypeError, ValueError):
        number = 2
    return f"v{max(number, 2)}"


def create_baseline(root: str | Path, project_id: str, payload: dict | None = None) -> dict:
    """Create a new draft baseline by copying the current confirmed baseline."""
    if payload is not None and not isinstance(payload, dict):
        raise BaselineValidationError("payload must be an object")
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        project_meta = _load_project_meta(project, project_id)
        source_id = (payload or {}).get("source_version_id") or project_meta.get(
            "current_baseline_version_id"
        )
        if not isinstance(source_id, str) or not safe_id(source_id):
            raise BaselineValidationError("source_version_id 非法")
        if source_id != project_meta.get("current_baseline_version_id"):
            raise BaselineConflict("只能从当前户型版本创建新版本")
        source_meta = _load_baseline_meta(project, source_id)
        if source_meta.get("status") != "confirmed":
            raise BaselineConflict("只能从已确认户型版本创建新版本")

        target_id = (payload or {}).get("id")
        if target_id is not None:
            if not isinstance(target_id, str) or not safe_id(target_id):
                raise BaselineValidationError("baseline id 非法")
        else:
            target_id = _next_version_id(project_meta)
        if _baseline_dir(project, target_id).exists():
            raise BaselineConflict(f"baseline {target_id!r} already exists")

        now = _now()
        target_dir = _baseline_dir(project, target_id)
        target_dir.mkdir(parents=True, exist_ok=False)
        source_geometry = _baseline_geometry_path(project, source_id)
        if source_id == "v1" and not source_geometry.exists():
            source_geometry = _root_geometry_path(project)
        if not source_geometry.exists():
            raise BaselineNotFound(f"source baseline {source_id!r} geometry not found")
        _atomic_write_bytes(_baseline_geometry_path(project, target_id), source_geometry.read_bytes())
        # 家具随户型一起复制到新版本 (Phase A): 新草稿从源版本标准布局起步继续编辑。
        # 源版本 furniture.json 缺失 (v1 未物化, 或 Phase A 之前创建的旧版本从未落家具)
        # 一律回退根 furniture.json (= 初始方案家具)。修复: 从 Phase-A-前的旧版本复制会得空家具。
        source_furniture = _baseline_furniture_path(project, source_id)
        if not source_furniture.exists():
            source_furniture = _root_furniture_path(project)
        if source_furniture.exists():
            _atomic_write_bytes(
                _baseline_furniture_path(project, target_id), source_furniture.read_bytes()
            )
        # 新户型版本默认复制照片引用 (§8.3); 引用同一批上传文件, 可在新版本重新标注。
        source_photos = _baseline_photos_path(project, source_id)
        if source_photos.exists():
            _atomic_write_bytes(_baseline_photos_path(project, target_id), source_photos.read_bytes())
        meta = {
            "id": target_id,
            "status": "draft",
            "source_version_id": source_id,
            "created_at": now,
            "confirmed_at": None,
            "superseded_at": None,
        }
        _persist_baseline_meta(project, target_id, meta)
        atomic_write_json(_baseline_validation_path(project, target_id), _validation_payload(project, target_id), indent=2)

        project_meta["next_baseline_version"] = max(
            int(str(target_id)[1:]) + 1 if str(target_id).startswith("v") and str(target_id)[1:].isdigit() else 2,
            int(project_meta.get("next_baseline_version", 2) or 2),
        )
        project_meta["updated_at"] = now
        atomic_write_json(_project_json_path(project), project_meta, indent=2)
        return meta


def initialize_new_project(
    root: str | Path,
    project_id: str,
    *,
    name: str | None,
    geometry_payload: dict,
) -> dict:
    """Create baseline metadata for a newly-created project.

    New projects start with ``v1`` in ``draft`` and no current confirmed baseline,
    so scheme creation is blocked until the user confirms the floorplan.
    """
    project = _project_dir(root, project_id)
    now = _now()
    project_meta = {
        "id": project_id,
        "name": name or _project_name_from_geometry(project, project_id),
        "current_baseline_version_id": None,
        "next_baseline_version": 2,
        "created_at": now,
        "updated_at": now,
    }
    baseline_meta = {
        "id": "v1",
        "status": "draft",
        "source_version_id": None,
        "created_at": now,
        "confirmed_at": None,
        "superseded_at": None,
    }
    atomic_write_json(_project_json_path(project), project_meta, indent=2)
    atomic_write_json(_baseline_meta_path(project, "v1"), baseline_meta, indent=2)
    atomic_write_json(_baseline_geometry_path(project, "v1"), geometry_payload, indent=2)
    atomic_write_json(_baseline_validation_path(project, "v1"), _validation_payload(project, "v1"), indent=2)
    return {"project": project_meta, "baseline": baseline_meta}


PHOTO_FIELDS = ("room_id", "direction", "note", "purpose")
# 拍摄视角 (升级: 实拍对齐): v0..v3 = 轴测绕房间中心转 0/90/180/270°, 使参考图从与照片
# 同侧的"角"看进去, 家具落到对的墙。前端以"所见即所得"缩略图让用户挑, 故用不透明编码。
# 旧值 N/S/E/W (仅文字提示、无几何对齐) 视作未设 (不旋转), 读时安全, 重选即写新值。
PHOTO_DIRECTIONS = {"v0", "v1", "v2", "v3"}
# 照片用途 (P2 材质C): empty=空房底图 (第7步结构锚, 缺省/None 亦按此); wall_material=墙面
# 实拍材质参考图 (由 walls[side].photo_id 引用, 注入 img2img edits)。
PHOTO_PURPOSES = {"empty", "wall_material", "underlay"}  # underlay=P6 底图描摹
# 每户型版本照片上限 (审计 P2-2): uploads 是唯一无界磁盘增长向量。
MAX_PHOTOS_PER_BASELINE = int(os.environ.get("AI_MAX_PHOTOS_PER_BASELINE", "") or 50)


def _validate_photo_fields(fields: dict) -> None:
    """标注字段白名单校验 (审计 P1-5): direction 只收 v0..v3 (拍摄视角 -> 轴测旋转对齐)。
    purpose (P2 材质C) 只收枚举, 决定照片是空房底图还是墙面材质参考。"""
    for key in PHOTO_FIELDS:
        if key in fields:
            value = fields[key]
            if value is not None and not isinstance(value, str):
                raise BaselineValidationError(f"{key} 必须为字符串或 null")
    direction = fields.get("direction")
    if direction is not None and direction not in PHOTO_DIRECTIONS:
        raise BaselineValidationError(
            f"direction 必须为 {sorted(PHOTO_DIRECTIONS)} 之一或 null"
        )
    purpose = fields.get("purpose")
    if purpose is not None and purpose not in PHOTO_PURPOSES:
        raise BaselineValidationError(
            f"purpose 必须为 {sorted(PHOTO_PURPOSES)} 之一或 null"
        )


def _baseline_photos_path(project: Path, version_id: str) -> Path:
    return _baseline_dir(project, version_id) / "photos.json"


def list_photos(root: str | Path, project_id: str, version_id: str) -> list[dict]:
    """空房照片列表 (绑定户型版本, 不绑定方案 — §8.3)。纯读, 未迁移项目不落盘。"""
    project = _project_dir(root, project_id)
    _load_baseline_meta(project, version_id)
    data = _read_json(_baseline_photos_path(project, version_id))
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    raise BaselineValidationError("photos.json 格式不受支持 (需数组), 请升级服务")


def _assert_photo_writable(meta: dict) -> None:
    if meta.get("status") == "superseded":
        raise BaselineConflict("历史户型版本不能修改空房照片")


def add_photo(root: str | Path, project_id: str, version_id: str, entry: dict) -> dict:
    _validate_photo_fields(entry)
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        _assert_photo_writable(_load_baseline_meta(project, version_id))
        path = _baseline_photos_path(project, version_id)
        data = _read_json(path)
        photos = data if isinstance(data, list) else []
        if len(photos) >= MAX_PHOTOS_PER_BASELINE:
            raise BaselineConflict(
                f"该户型版本照片已达上限 {MAX_PHOTOS_PER_BASELINE} 张, 请先删除无用照片"
            )
        photos.insert(0, entry)
        atomic_write_json(path, photos, indent=2)
        return entry


def update_photo(
    root: str | Path, project_id: str, version_id: str, photo_id: str, fields: dict
) -> dict:
    """标注照片 (房间/拍摄方向/备注 — §8.3)。仅白名单字段。"""
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        _assert_photo_writable(_load_baseline_meta(project, version_id))
        path = _baseline_photos_path(project, version_id)
        data = _read_json(path)
        photos = data if isinstance(data, list) else []
        for photo in photos:
            if photo.get("id") == photo_id:
                _validate_photo_fields(fields)
                for key in PHOTO_FIELDS:
                    if key in fields:
                        photo[key] = fields[key]
                photo["updated_at"] = _now()
                atomic_write_json(path, photos, indent=2)
                return photo
        raise BaselineNotFound(f"照片 {photo_id!r} 不存在")


def set_photo_calibration(
    root: str | Path, project_id: str, version_id: str, photo_id: str, calibration: dict
) -> dict:
    """存透视标定到照片记录 (P2b 几何锁定): calibration = {x_lines,y_lines,anchors,img_wh,camera}。

    与 update_photo 并列但走独立通道 (标定是复杂对象, 不进 PHOTO_FIELDS 简单白名单)。
    透视标定是照片的元数据 (相机参数), 不改照片内容/历史成果; 且 render-real 本就用方案绑定的
    (可能已 superseded 的) 历史版本照片出图 —— 故【允许历史版本标定】, 不走 _assert_photo_writable。
    """
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        _load_baseline_meta(project, version_id)  # 仅校验版本存在 (缺则抛), 不拦 superseded
        path = _baseline_photos_path(project, version_id)
        data = _read_json(path)
        photos = data if isinstance(data, list) else []
        for photo in photos:
            if photo.get("id") == photo_id:
                photo["calibration"] = calibration
                photo["updated_at"] = _now()
                atomic_write_json(path, photos, indent=2)
                return photo
        raise BaselineNotFound(f"照片 {photo_id!r} 不存在")


def delete_photo(root: str | Path, project_id: str, version_id: str, photo_id: str) -> dict:
    """删除照片引用 (文件本身保留 — 历史成果不受影响, 由独立清理策略处理; §8.3/§12)。"""
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        _assert_photo_writable(_load_baseline_meta(project, version_id))
        path = _baseline_photos_path(project, version_id)
        data = _read_json(path)
        photos = data if isinstance(data, list) else []
        remaining = [p for p in photos if p.get("id") != photo_id]
        if len(remaining) == len(photos):
            raise BaselineNotFound(f"照片 {photo_id!r} 不存在")
        atomic_write_json(path, remaining, indent=2)
        return {"ok": True, "removed": photo_id}


def validate_baseline(root: str | Path, project_id: str, version_id: str) -> dict:
    _ensure_project_structure(root, project_id)
    project = _project_dir(root, project_id)
    _load_baseline_meta(project, version_id)
    payload = _validation_payload(project, version_id)
    atomic_write_json(_baseline_validation_path(project, version_id), payload, indent=2)
    return payload


def save_baseline_geometry(
    root: str | Path,
    project_id: str,
    version_id: str,
    geometry_payload: dict,
) -> dict:
    if not isinstance(geometry_payload, dict):
        raise BaselineValidationError("geometry body must be an object")
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        meta = _load_baseline_meta(project, version_id)
        if meta.get("status") != "draft":
            raise BaselineConflict("已确认或历史户型版本不能保存修改")

        try:
            from floorplan_core import geometry as geometry_core

            issues = geometry_core.validate(geometry_payload)
        except Exception as exc:  # noqa: BLE001
            raise BaselineValidationError(str(exc)) from exc
        errors = [message for level, message in issues if level == "ERROR"]
        warns = [message for level, message in issues if level == "WARN"]
        if errors:
            return {"ok": False, "errors": errors, "warns": warns}

        atomic_write_json(_baseline_geometry_path(project, version_id), geometry_payload, indent=2)
        validation_payload = {
            "version_id": version_id,
            "validated_at": _now(),
            "issues": [{"level": level, "message": message} for level, message in issues],
        }
        atomic_write_json(_baseline_validation_path(project, version_id), validation_payload, indent=2)
        return {"ok": True, "warns": warns, "validation": validation_payload}


def save_baseline_furniture(
    root: str | Path,
    project_id: str,
    version_id: str,
    furniture: list,
) -> dict:
    """保存基线标准布局家具 (Phase A): 仅草稿版本可写, 与几何同"确认即只读"。

    家具是纯布局数据 (不经 validate 的 ERROR 门, 场景校验在渲染期做); 原子写盘。
    不镜像到根 furniture.json —— 根文件是定稿冻结基线 (golden 读它), 保持字节不变。
    """
    if not isinstance(furniture, list):
        raise BaselineValidationError("furniture body must be an array")
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        meta = _load_baseline_meta(project, version_id)
        if meta.get("status") != "draft":
            raise BaselineConflict("已确认或历史户型版本不能保存修改")
        atomic_write_json(_baseline_furniture_path(project, version_id), furniture, indent=1)
        return {"ok": True, "count": len(furniture)}


def _demote_stale_confirmed(project: Path, *, keep: str, now: str) -> None:
    """Enforce «至多一个 confirmed = 当前指针»:把除 keep 外仍为 confirmed 的版本降级 superseded。

    幂等自愈:即使某次 confirm 在中途崩溃留下两个 confirmed,下次 confirm(或重入)会收敛。
    """
    for vid in _existing_version_ids(project):
        if vid == keep:
            continue
        data = _read_json(_baseline_meta_path(project, vid))
        if isinstance(data, dict) and data.get("status") == "confirmed":
            demoted = dict(data)
            demoted["status"] = "superseded"
            demoted["superseded_at"] = now
            _persist_baseline_meta(project, vid, demoted)


def confirm_baseline(root: str | Path, project_id: str, version_id: str) -> dict:
    """确认户型版本。

    崩溃安全排序(单个 project_lock 内串行):
      1. 目标 draft → 重校验磁盘草稿几何(有 ERROR 不改任何状态);置目标为 confirmed。
      2. 镜像目标几何到根 geometry.json(幂等)。
      3. **提交点**:切换 project.json 当前指针到目标。
      4. **提交后自愈**:降级除当前外所有残留 confirmed 版本 → superseded。

    任一步骤间崩溃时,`current` 指针始终指向某个 confirmed 版本(不会指向 superseded),
    故 legacy /save-geometry 的「当前已确认只读」门禁不会失效;重试 confirm 可从部分提交恢复。
    """
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        project_meta = _load_project_meta(project, project_id)
        target_meta = _load_baseline_meta(project, version_id)
        current_id = project_meta.get("current_baseline_version_id")
        status = target_meta.get("status")
        now = _now()

        # 幂等:目标已是当前确认版本 → 无需变更,仅做一次历史版本降级自愈后返回。
        if status == "confirmed" and current_id == version_id:
            _demote_stale_confirmed(project, keep=version_id, now=now)
            return {
                "ok": True,
                "project": _load_project_meta(project, project_id),
                "baseline": _load_baseline_meta(project, version_id),
            }

        # 允许:draft 正常确认;或从「部分提交」(目标已 confirmed 但指针未切)恢复。
        if status not in ("draft", "confirmed"):
            raise BaselineConflict("只能确认 draft 户型版本")

        # 步 1:draft 路径先重校验并置 confirmed(confirmed 恢复路径跳过,几何已固化)。
        if status == "draft":
            validation_payload = _validation_payload(project, version_id)
            errors = [
                issue.get("message")
                for issue in validation_payload.get("issues", [])
                if isinstance(issue, dict) and issue.get("level") == "ERROR"
            ]
            if errors:
                atomic_write_json(_baseline_validation_path(project, version_id), validation_payload, indent=2)
                raise BaselineValidationError({"errors": errors})
            target_meta["status"] = "confirmed"
            target_meta["confirmed_at"] = now
            target_meta["superseded_at"] = None
            _persist_baseline_meta(project, version_id, target_meta)
            atomic_write_json(_baseline_validation_path(project, version_id), validation_payload, indent=2)

        # 步 2:镜像目标几何到根(幂等,相同字节)。
        target_geometry = _baseline_geometry_path(project, version_id)
        if not target_geometry.exists():
            raise BaselineNotFound(f"baseline {version_id!r} geometry not found")
        _atomic_write_bytes(_root_geometry_path(project), target_geometry.read_bytes())

        # 步 3(提交点):切换当前指针。此前崩溃 → 指针仍指旧 confirmed 版本,门禁不失效,可重试。
        project_meta["current_baseline_version_id"] = version_id
        project_meta["updated_at"] = now
        atomic_write_json(_project_json_path(project), project_meta, indent=2)

        # 步 4(提交后自愈):降级除当前外所有残留 confirmed 版本。
        _demote_stale_confirmed(project, keep=version_id, now=now)

        return {
            "ok": True,
            "project": _load_project_meta(project, project_id),
            "baseline": _load_baseline_meta(project, version_id),
        }


def _schemes_bound_to(project: Path, version_id: str) -> list[str]:
    """列出 meta.baseline_version_id == version_id 的方案 id (删除版本的级联真源)。

    与 schemes.list_schemes 同口径按版本过滤; 直接读 meta 避免 baselines→schemes 循环依赖。
    排除 default: default 是 fallback 方案 (delete_scheme 亦禁删), 其 baseline_version_id
    一次性 pin 不随 confirm 迁移, 级联删会破坏 fallback 语义 —— 留存, 由 _ensure_default 自愈。
    """
    bound: list[str] = []
    for scheme_id in _scheme_ids(project):
        if scheme_id == "default":
            continue
        data = _read_json(_scheme_meta_path(project, scheme_id))
        if isinstance(data, dict) and data.get("baseline_version_id") == version_id:
            bound.append(scheme_id)
    return bound


def _repin_default_if_bound(project: Path, version_id: str, current_id: str | None) -> bool:
    """default 方案若 pin 到被删版本 → 改 pin 到 current (而非留悬空)。

    default 是 fallback 方案 (不进级联回收站), 其 baseline_version_id 一次性 pin 不随
    confirm 迁移。删掉它所 pin 的版本会使 default 悬空 → 渲染读错几何 / BaselineNotFound。
    删除时就地重 pin 到 current (删除保证 current≠被删版本, 故 current 必为存活版本)。
    直接改 meta 键 (不引 schemes 避循环); 未 materialize 的 default 无 meta 文件, 天然 pin current。
    """
    if not current_id:
        return False
    meta_path = _scheme_meta_path(project, "default")
    data = _read_json(meta_path)
    if not isinstance(data, dict) or data.get("baseline_version_id") != version_id:
        return False
    data["baseline_version_id"] = current_id
    data["updated_at"] = _now()
    atomic_write_json(meta_path, data, indent=2)
    return True


def delete_baseline(root: str | Path, project_id: str, version_id: str) -> dict:
    """软删户型版本 (级联移绑定方案入回收站; §版本管理)。

    前置校验 (违反 → BaselineConflict 409):
      - 禁删 v1: v1 与根 geometry.json 硬绑定 (唯一被 list/read/migrate 合成兜底的版本),
        删目录后下次写操作会经 migrate_project 用根几何 (已镜像成 current) 把 v1 复活成
        confirmed → 破坏「至多一个 confirmed = current」不变量。故 v1 永不可删。
      - 只能删 draft / superseded (confirmed=当前版本不可删, 保 current 指针不变量)。
      - 不能删项目最后一个版本 (否则失去几何来源)。
    级联: 非 default 绑定方案 mv 到 schemes/.trash; default 方案若绑该版本则重 pin 到 current。
    软删: 版本目录 mv 到 baselines/.trash/{vN}-{ts} (不 rmtree, 可恢复)。
    共享上传文件 (uploads) / 效果图字节只解绑不物删 (对齐 delete_photo/delete_scheme)。
    next_baseline_version 不回退 (防 vN id 复用与 .trash 目录冲突)。
    """
    if not safe_id(version_id):
        raise BaselineValidationError("version_id 非法")
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        project_meta = _load_project_meta(project, project_id)
        current_id = project_meta.get("current_baseline_version_id")
        target_dir = _baseline_dir(project, version_id)
        if not target_dir.exists() or not target_dir.is_dir():
            raise BaselineNotFound(f"baseline {version_id!r} not found")
        meta = _load_baseline_meta(project, version_id)
        status = meta.get("status")

        if version_id == "v1":
            raise BaselineConflict("不能删除初始户型版本 v1（与根几何绑定）")
        if version_id == current_id or status == "confirmed":
            raise BaselineConflict("不能删除当前已确认户型版本;请先确认另一版本再删")
        if status not in ("draft", "superseded"):
            raise BaselineConflict("只能删除草稿或历史(被替代)户型版本")
        if len(_existing_version_ids(project)) <= 1:
            raise BaselineConflict("不能删除项目最后一个户型版本")

        now = _now()
        schemes_root = _schemes_dir(project)
        scheme_trash = schemes_root / ".trash"
        trashed_schemes: list[str] = []
        bound_schemes = _schemes_bound_to(project, version_id)
        if bound_schemes:
            scheme_trash.mkdir(parents=True, exist_ok=True)
        for scheme_id in bound_schemes:
            src = _scheme_dir(project, scheme_id)
            if not src.exists():
                continue
            ts = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            dest = scheme_trash / f"{scheme_id}-{ts}"
            shutil.move(str(src), str(dest))
            trashed_schemes.append(scheme_id)

        # default 悬空防护: 若 default pin 到被删版本, 就地重 pin 到 current。
        _repin_default_if_bound(project, version_id, current_id)

        baseline_trash = _baselines_dir(project) / ".trash"
        baseline_trash.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        dest = baseline_trash / f"{version_id}-{ts}"
        shutil.move(str(target_dir), str(dest))

        # project.json: 仅更新时间戳; next_baseline_version 保持单调 (不回退)。
        project_meta["updated_at"] = now
        atomic_write_json(_project_json_path(project), project_meta, indent=2)
        return {
            "ok": True,
            "trashed": dest.name,
            "schemes_trashed": trashed_schemes,
        }


def _default_scheme_meta(now: str, existing: dict | None = None) -> dict:
    """default 方案 meta 规范化 (与 schemes._normalize_meta 语义对齐 — 审计 P2 legacy 收口)。

    只有 name 保持强制 (UI 统一「初始方案」); status/baseline_version_id 用 setdefault ——
    此前无条件覆写会让 migrate_project 重跑把已确认、已绑 v2 的 default 方案
    静默改回 draft+v1 (破坏状态机与引用完整性)。
    """
    meta = dict(existing or {})
    meta.setdefault("id", "default")
    meta["name"] = "初始方案"
    meta.setdefault("source", "legacy")
    meta.setdefault("style_prompt", "")
    meta.setdefault("base_scheme_id", None)
    if meta.get("status") not in SCHEME_STATUSES:
        meta["status"] = "draft"
    meta.setdefault("created_at", now)
    meta.setdefault("updated_at", now)
    meta["baseline_version_id"] = meta.get("baseline_version_id") or "v1"
    meta.setdefault("preferred", False)
    meta.setdefault("archived_at", None)
    return meta


def _merge_scheme_meta(scheme_id: str, now: str, existing: dict | None) -> dict:
    if scheme_id == "default":
        return _default_scheme_meta(now, existing)
    meta = dict(existing or {})
    meta.setdefault("id", scheme_id)
    meta.setdefault("name", scheme_id)
    meta.setdefault("source", "manual")
    meta.setdefault("style_prompt", "")
    meta.setdefault("base_scheme_id", None)
    if meta.get("status") not in SCHEME_STATUSES:
        meta["status"] = "draft"
    meta.setdefault("created_at", now)
    meta.setdefault("updated_at", now)
    meta["baseline_version_id"] = meta.get("baseline_version_id") or "v1"
    meta.setdefault("preferred", False)
    meta.setdefault("archived_at", None)
    return meta


def _scheme_ids(project: Path) -> list[str]:
    root = _schemes_dir(project)
    if not root.exists():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(".") and safe_id(child.name)
    )


def _migrate_default_scheme(report: dict, project: Path, now: str, *, dry_run: bool) -> None:
    default_dir = _scheme_dir(project, "default")
    root_furniture = _root_furniture_path(project)
    if not default_dir.exists() and root_furniture.exists():
        _record(report, "create-dir", default_dir)
        if not dry_run:
            default_dir.mkdir(parents=True, exist_ok=True)
    existing_meta = _read_json(_scheme_meta_path(project, "default"))
    _write_json_if_changed(
        report,
        _scheme_meta_path(project, "default"),
        _default_scheme_meta(now, existing_meta if isinstance(existing_meta, dict) else None),
        dry_run=dry_run,
        indent=2,
        action="create-default-scheme-meta",
    )
    _copy_bytes_if_missing(
        report,
        root_furniture,
        _scheme_furniture_path(project, "default"),
        dry_run=dry_run,
        action="copy-default-furniture",
    )
    _write_json_if_changed(
        report,
        _scheme_renders_path(project, "default"),
        [],
        dry_run=dry_run,
        indent=None,
        action="create-default-renders",
    )


def _migrate_existing_scheme(
    report: dict,
    project: Path,
    scheme_id: str,
    now: str,
    *,
    dry_run: bool,
) -> None:
    existing_meta = _read_json(_scheme_meta_path(project, scheme_id))
    _write_json_if_changed(
        report,
        _scheme_meta_path(project, scheme_id),
        _merge_scheme_meta(scheme_id, now, existing_meta if isinstance(existing_meta, dict) else None),
        dry_run=dry_run,
        indent=2,
        action="create-scheme-meta",
    )
    if not _scheme_furniture_path(project, scheme_id).exists():
        _write_json_if_changed(
            report,
            _scheme_furniture_path(project, scheme_id),
            [],
            dry_run=dry_run,
            indent=1,
            action="create-empty-scheme-furniture",
        )
    if not _scheme_renders_path(project, scheme_id).exists():
        _write_json_if_changed(
            report,
            _scheme_renders_path(project, scheme_id),
            [],
            dry_run=dry_run,
            indent=None,
            action="create-scheme-renders",
        )


def migrate_project(
    root: str | Path,
    project_id: str,
    *,
    dry_run: bool = True,
    backup: bool = False,
    now: str | None = None,
) -> dict:
    """Migrate one legacy file-backed project to baseline-aware structure.

    Dry-run returns the same operation plan without writing. Apply mode is
    idempotent: rerunning after a successful migration produces no operations.
    Root ``geometry.json`` and ``furniture.json`` are never rewritten here.
    """
    project = _project_dir(root, project_id)
    root_geometry = _root_geometry_path(project)
    if not root_geometry.exists():
        raise BaselineNotFound(f"project {project_id!r} missing geometry.json")

    ts = now or _now()
    report = {
        "project_id": project_id,
        "dry_run": dry_run,
        "backup_path": None,
        "operations": [],
        "warnings": [],
    }

    lock_ctx = nullcontext() if dry_run else project_lock(root, project_id, timeout_s=10)
    with lock_ctx:
        if backup and not dry_run:
            backup_root = Path(root) / ".backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            dest = backup_root / f"{project_id}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}"
            shutil.copytree(project, dest, ignore=shutil.ignore_patterns(".project.lock"))
            report["backup_path"] = str(dest)

        project_meta = _merge_project_meta(project, project_id, ts)
        _write_json_if_changed(
            report,
            _project_json_path(project),
            project_meta,
            dry_run=dry_run,
            indent=2,
            action="create-project-meta",
        )

        _copy_bytes_if_missing(
            report,
            root_geometry,
            _baseline_geometry_path(project, "v1"),
            dry_run=dry_run,
            action="copy-baseline-geometry",
        )
        # 家具下沉基线 (Phase A): v1 标准布局家具 = 根 furniture.json (= 初始方案家具)。
        # 源缺失只告警不阻断 (新建项目由 initialize_new_project 走另一路)。
        _copy_bytes_if_missing(
            report,
            _root_furniture_path(project),
            _baseline_furniture_path(project, "v1"),
            dry_run=dry_run,
            action="copy-baseline-furniture",
        )
        _write_json_if_changed(
            report,
            _baseline_meta_path(project, "v1"),
            _merge_baseline_v1_meta(project, ts),
            dry_run=dry_run,
            indent=2,
            action="create-baseline-meta",
        )
        _write_json_if_missing(
            report,
            _baseline_validation_path(project, "v1"),
            _validation_payload(project, "v1"),
            dry_run=dry_run,
            indent=2,
            action="create-baseline-validation",
        )

        _migrate_default_scheme(report, project, ts, dry_run=dry_run)
        for scheme_id in _scheme_ids(project):
            if scheme_id == "default":
                continue
            _migrate_existing_scheme(report, project, scheme_id, ts, dry_run=dry_run)

    report["changed"] = bool(report["operations"])
    return report


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate file-backed projects to baseline model")
    parser.add_argument("--data-dir", required=True, help="Directory containing project folders")
    parser.add_argument("--project", required=True, help="Project id, e.g. D")
    parser.add_argument("--apply", action="store_true", help="Write changes instead of dry-run")
    parser.add_argument("--backup", action="store_true", help="Copy project to .backups before apply")
    args = parser.parse_args(argv)

    report = migrate_project(
        args.data_dir,
        args.project,
        dry_run=not args.apply,
        backup=args.backup,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
