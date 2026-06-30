# -*- coding: utf-8 -*-
"""Project baseline storage and migration helpers.

Stage 0 intentionally keeps this module independent from the active API routes:
it provides the file model, project-level lock, and idempotent migration/dry-run
that later stages can use without changing existing production read/write paths.
"""
from __future__ import annotations

import argparse
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
    """Acquire an exclusive project-level filesystem lock.

    This is deliberately small and local-process agnostic: it uses O_EXCL on
    ``{project}/.project.lock`` so separate API workers also serialize critical
    sections. Later baseline confirmation can reuse this lock.
    """
    project = _project_dir(root, project_id)
    lock_path = project / ".project.lock"
    deadline = time.monotonic() + timeout_s
    fd: int | None = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = f"pid={os.getpid()} created_at={_now()}\n".encode("utf-8")
            os.write(fd, payload)
            os.fsync(fd)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise BaselineConflict(f"project {project_id!r} is locked") from exc
            time.sleep(poll_s)
    try:
        yield lock_path
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


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
        return meta
    if version_id == "v1" and _root_geometry_path(project).exists():
        return _synthetic_baseline_v1_meta()
    raise BaselineNotFound(f"baseline {version_id!r} not found")


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
        meta = {
            "id": target_id,
            "status": "draft",
            "source_version_id": source_id,
            "created_at": now,
            "confirmed_at": None,
            "superseded_at": None,
        }
        atomic_write_json(_baseline_meta_path(project, target_id), meta, indent=2)
        atomic_write_json(_baseline_validation_path(project, target_id), _validation_payload(project, target_id), indent=2)

        project_meta["next_baseline_version"] = max(
            int(str(target_id)[1:]) + 1 if str(target_id).startswith("v") and str(target_id)[1:].isdigit() else 2,
            int(project_meta.get("next_baseline_version", 2) or 2),
        )
        project_meta["updated_at"] = now
        atomic_write_json(_project_json_path(project), project_meta, indent=2)
        return meta


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


def confirm_baseline(root: str | Path, project_id: str, version_id: str) -> dict:
    _ensure_project_structure(root, project_id)
    with project_lock(root, project_id):
        project = _project_dir(root, project_id)
        project_meta = _load_project_meta(project, project_id)
        target_meta = _load_baseline_meta(project, version_id)
        if target_meta.get("status") != "draft":
            raise BaselineConflict("只能确认 draft 户型版本")
        validation_payload = _validation_payload(project, version_id)
        errors = [
            issue.get("message")
            for issue in validation_payload.get("issues", [])
            if isinstance(issue, dict) and issue.get("level") == "ERROR"
        ]
        if errors:
            atomic_write_json(_baseline_validation_path(project, version_id), validation_payload, indent=2)
            raise BaselineValidationError({"errors": errors})

        now = _now()
        current_id = project_meta.get("current_baseline_version_id")
        if isinstance(current_id, str) and current_id != version_id:
            current_meta = _load_baseline_meta(project, current_id)
            if current_meta.get("status") == "confirmed":
                current_meta["status"] = "superseded"
                current_meta["superseded_at"] = now
                atomic_write_json(_baseline_meta_path(project, current_id), current_meta, indent=2)

        target_meta["status"] = "confirmed"
        target_meta["confirmed_at"] = now
        target_meta["superseded_at"] = None
        atomic_write_json(_baseline_meta_path(project, version_id), target_meta, indent=2)
        atomic_write_json(_baseline_validation_path(project, version_id), validation_payload, indent=2)

        target_geometry = _baseline_geometry_path(project, version_id)
        if not target_geometry.exists():
            raise BaselineNotFound(f"baseline {version_id!r} geometry not found")
        _atomic_write_bytes(_root_geometry_path(project), target_geometry.read_bytes())

        project_meta["current_baseline_version_id"] = version_id
        project_meta["updated_at"] = now
        atomic_write_json(_project_json_path(project), project_meta, indent=2)
        return {"ok": True, "project": project_meta, "baseline": target_meta}


def _default_scheme_meta(now: str, existing: dict | None = None) -> dict:
    meta = dict(existing or {})
    meta.setdefault("id", "default")
    meta["name"] = "初始方案"
    meta.setdefault("source", "legacy")
    meta.setdefault("style_prompt", "")
    meta.setdefault("base_scheme_id", None)
    meta["status"] = "draft"
    meta.setdefault("created_at", now)
    meta.setdefault("updated_at", now)
    meta["baseline_version_id"] = "v1"
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
