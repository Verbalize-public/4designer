"""Simple project persistence for 4designer (JSON + proxy GLBs under daemon/projects)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("fourdesigner.persistence")

PROJECTS_DIR = Path(__file__).resolve().parents[1] / "projects"
LAST_SLUG_FILE = PROJECTS_DIR / "_last_slug.txt"


def ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def project_path(slug: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug) or "default"
    return PROJECTS_DIR / f"{safe}.json"


def proxies_dir(slug: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug) or "default"
    d = PROJECTS_DIR / safe / "proxies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def render_proxies_dir(slug: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug) or "default"
    d = PROJECTS_DIR / safe / "render_proxy"
    d.mkdir(parents=True, exist_ok=True)
    return d


def proxy_file(slug: str, oid: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in oid) or "obj"
    return proxies_dir(slug) / f"{safe_id}.glb"


def render_proxy_file(slug: str, oid: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in oid) or "obj"
    return render_proxies_dir(slug) / f"{safe_id}.glb"


def write_proxy_bytes(slug: str, oid: str, data: bytes) -> Path:
    path = proxy_file(slug, oid)
    path.write_bytes(data)
    return path


def write_render_proxy_bytes(slug: str, oid: str, data: bytes) -> Path:
    path = render_proxy_file(slug, oid)
    path.write_bytes(data)
    return path


def read_proxy_bytes(slug: str, oid: str) -> Optional[bytes]:
    path = proxy_file(slug, oid)
    if not path.exists():
        return None
    return path.read_bytes()


def read_render_proxy_bytes(slug: str, oid: str) -> Optional[bytes]:
    path = render_proxy_file(slug, oid)
    if not path.exists():
        return None
    return path.read_bytes()


def delete_proxy_file(slug: str, oid: str) -> bool:
    path = proxy_file(slug, oid)
    if path.exists():
        path.unlink()
        return True
    return False


def delete_render_proxy_file(slug: str, oid: str) -> bool:
    path = render_proxy_file(slug, oid)
    if path.exists():
        path.unlink()
        return True
    return False


def delete_all_proxies(slug: str) -> None:
    d = PROJECTS_DIR / (
        "".join(c if c.isalnum() or c in "-_" else "_" for c in slug) or "default"
    )
    proxies = d / "proxies"
    if proxies.exists():
        shutil.rmtree(proxies, ignore_errors=True)


def write_project(state: dict[str, Any], slug: str) -> Path:
    ensure_dirs()
    path = project_path(slug)
    payload = {
        "schema_version": state.get("schema_version", 1),
        "layers": state.get("layers", {}),
        "objects": state.get("objects", {}),
        "selection": state.get("selection", []),
        "slug": slug,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    LAST_SLUG_FILE.write_text(slug, encoding="utf-8")
    return path


def read_project(slug: str) -> Optional[dict[str, Any]]:
    path = project_path(slug)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("failed to read project %s", slug)
        return None


def last_slug() -> str:
    ensure_dirs()
    if LAST_SLUG_FILE.exists():
        s = LAST_SLUG_FILE.read_text(encoding="utf-8").strip()
        if s:
            return s
    return "default"


def migrate_and_boot() -> tuple[str, Optional[dict[str, Any]]]:
    ensure_dirs()
    slug = last_slug()
    return slug, read_project(slug)
