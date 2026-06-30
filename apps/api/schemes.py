# -*- coding: utf-8 -*-
"""FurnitureScheme storage helpers.

Project geometry remains project-scoped. Furniture and render history can be
scheme-scoped under {project}/schemes/{scheme_id}/ while legacy root
furniture.json remains the default compatibility surface.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ALLOWED_SOURCES = {"legacy", "manual", "duplicate", "ai"}
_ALLOWED_STATUS = {"draft", "confirmed"}


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
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _load_furniture_file(path: Path) -> list:
    data = _read_json(path, [])
    return data if isinstance(data, list) else []


def _default_meta(*, virtual: bool) -> dict:
    ts = None if virtual else _now()
    return {
        "id": "default",
        "name": "默认方案",
        "source": "legacy",
        "style_prompt": "",
        "base_scheme_id": None,
        "status": "confirmed",
        "created_at": ts,
        "updated_at": ts,
    }


def _load_meta(project: Path, scheme_id: str) -> dict:
    if scheme_id == "default" and not _meta_path(project, "default").exists():
        return _default_meta(virtual=True)
    meta_path = _meta_path(project, scheme_id)
    if not meta_path.exists():
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
    data = _read_json(meta_path, None)
    if not isinstance(data, dict):
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
    return data


def _ensure_default(project: Path) -> None:
    default_dir = _scheme_dir(project, "default")
    if default_dir.exists():
        return
    root_furniture = _root_furniture_path(project)
    if not root_furniture.exists():
        raise SchemeNotFound("root furniture.json not found")
    default_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root_furniture, default_dir / "furniture.json")
    _atomic_write_json(default_dir / "meta.json", _default_meta(virtual=False), indent=2)
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


def _summary(project: Path, scheme_id: str) -> dict:
    meta = _load_meta(project, scheme_id)
    items = len(read_furniture(project.parent, project.name, scheme_id))
    renders = len(list_renders(project.parent, project.name, scheme_id))
    return {
        "id": meta.get("id", scheme_id),
        "name": meta.get("name") or scheme_id,
        "source": meta.get("source") or "manual",
        "status": meta.get("status") or "draft",
        "items": items,
        "renders": renders,
        "updated_at": meta.get("updated_at"),
    }


def list_schemes(root: str | Path, project_id: str) -> list[dict]:
    project = _project_dir(root, project_id)
    schemes_root = _schemes_dir(project)
    if not schemes_root.exists():
        return [_summary(project, "default")]
    out: list[dict] = []
    for child in sorted(schemes_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            out.append(_summary(project, child.name))
        except SchemeNotFound:
            continue
    if not any(item["id"] == "default" for item in out):
        out.insert(0, _summary(project, "default"))
    return out


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
    if source not in _ALLOWED_SOURCES - {"legacy"}:
        raise SchemeValidationError("source 非法")
    furniture = payload.get("furniture", [])
    if not isinstance(furniture, list):
        raise SchemeValidationError("furniture must be an array")
    target = _scheme_dir(project, scheme_id)
    if target.exists():
        raise SchemeConflict(f"scheme {scheme_id!r} already exists")
    _ensure_default(project)
    now = _now()
    meta = {
        "id": scheme_id,
        "name": payload.get("name") or scheme_id,
        "source": source,
        "style_prompt": payload.get("style_prompt") or "",
        "base_scheme_id": payload.get("base_scheme_id"),
        "status": payload.get("status") if payload.get("status") in _ALLOWED_STATUS else "draft",
        "created_at": now,
        "updated_at": now,
    }
    target.mkdir(parents=True, exist_ok=False)
    _atomic_write_json(target / "meta.json", meta, indent=2)
    _atomic_write_json(target / "furniture.json", furniture, indent=1)
    _atomic_write_json(target / "renders.json", [], indent=None)
    return meta


def duplicate_scheme(root: str | Path, project_id: str, source_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
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
        "name": payload.get("name") or f"{source_id} 副本",
        "source": "duplicate",
        "style_prompt": "",
        "base_scheme_id": source_id,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    target.mkdir(parents=True, exist_ok=False)
    _atomic_write_json(target / "meta.json", meta, indent=2)
    _atomic_write_json(target / "furniture.json", furniture, indent=1)
    _atomic_write_json(target / "renders.json", [], indent=None)
    return meta


def patch_scheme(root: str | Path, project_id: str, scheme_id: str, payload: dict) -> dict:
    project = _project_dir(root, project_id)
    if not isinstance(payload, dict):
        raise SchemeValidationError("payload must be an object")
    _ensure_default(project)
    meta = _load_meta(project, scheme_id)
    if "name" in payload:
        if not isinstance(payload["name"], str) or not payload["name"].strip():
            raise SchemeValidationError("name must be a non-empty string")
        meta["name"] = payload["name"].strip()
    if "status" in payload:
        if payload["status"] not in _ALLOWED_STATUS:
            raise SchemeValidationError("status 非法")
        meta["status"] = payload["status"]
    meta["updated_at"] = _now()
    _atomic_write_json(_meta_path(project, scheme_id), meta, indent=2)
    return meta


def delete_scheme(root: str | Path, project_id: str, scheme_id: str) -> dict:
    project = _project_dir(root, project_id)
    if scheme_id == "default":
        raise SchemeError("default scheme cannot be deleted")
    target = _scheme_dir(project, scheme_id)
    if not target.exists() or not target.is_dir():
        raise SchemeNotFound(f"scheme {scheme_id!r} not found")
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
    path = _furniture_path(project, scheme_id)
    _atomic_write_json(path, furniture, indent=1)
    if scheme_id == "default":
        _atomic_write_json(_root_furniture_path(project), furniture, indent=1)
    meta = _load_meta(project, scheme_id)
    meta["updated_at"] = _now()
    _atomic_write_json(_meta_path(project, scheme_id), meta, indent=2)
    return {"ok": True}


def list_renders(root: str | Path, project_id: str, scheme_id: str = "default") -> list:
    project = _project_dir(root, project_id)
    _require_scheme(project, scheme_id)
    data = _read_json(_renders_path(project, scheme_id), [])
    return data if isinstance(data, list) else []


def append_render(
    root: str | Path, project_id: str, scheme_id: str, record: dict, *, cap: int = 200
) -> None:
    project = _project_dir(root, project_id)
    _ensure_default(project)
    _require_scheme(project, scheme_id)
    items = list_renders(root, project_id, scheme_id)
    items.insert(0, record)
    del items[cap:]
    _atomic_write_json(_renders_path(project, scheme_id), items, indent=None)
