"""Render-view SOT: one-shot scene snapshot + separate undo from marshals."""

from __future__ import annotations

import copy
import hashlib
import time
import uuid
from typing import Any, Optional

from .state import normalize_bounds, normalize_proxy_meta, normalize_proxy_mode, normalize_trs

MAX_RENDER_OBJECTS = 256
PREVIEW_PENDING_TIMEOUT_S = 2.0
ICON_BOUNDS = {
    "min": [-0.25, -0.25, -0.25],
    "max": [0.25, 0.25, 0.25],
}


def empty_render_state() -> dict[str, Any]:
    return {
        "render_path": "",
        "tops": [],
        "objects": {},
        "selection": [],
        "status": "",
        "counts": {"geo": 0, "light": 0, "camera": 0},
    }


def _stable_id(td_path: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "4designer-render:" + td_path))


def _round_vec(v: Any, nd: int = 4) -> list[float]:
    if not isinstance(v, (list, tuple)):
        return [0.0, 0.0, 0.0]
    out: list[float] = []
    for i in range(3):
        try:
            out.append(round(float(v[i]), nd))
        except (IndexError, TypeError, ValueError):
            out.append(0.0)
    return out


def plate_content_fingerprint(objects: dict[str, Any], render_path: str = "") -> str:
    """Stable hash of plate structure + TRS/bounds (ignores proxy beauty / selection)."""
    parts: list[str] = [str(render_path or "")]
    for oid in sorted(objects.keys()):
        o = objects[oid]
        if not isinstance(o, dict):
            continue
        trs = o.get("trs") or {}
        bounds = o.get("bounds") or {}
        parts.append(
            "|".join(
                [
                    str(oid),
                    str(o.get("td_path") or ""),
                    str(o.get("kind") or ""),
                    str(o.get("name") or ""),
                    str(o.get("op_type") or ""),
                    str(o.get("light_type") or ""),
                    str(round(float(o.get("cone_angle") or 0.0), 2)),
                    str(_round_vec(trs.get("t"))),
                    str(_round_vec(trs.get("r"))),
                    str(_round_vec(trs.get("s"))),
                    str(_round_vec(bounds.get("min"))),
                    str(_round_vec(bounds.get("max"))),
                ]
            )
        )
    raw = "\n".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def normalize_plate_object(body: dict[str, Any], *, prev: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    td_path = str(body.get("td_path") or "")
    kind = str(body.get("kind") or "geo").strip().lower()
    if kind not in ("geo", "light", "env_light", "camera"):
        kind = "geo"
    oid = str(body.get("id") or "") or (_stable_id(td_path) if td_path else str(uuid.uuid4()))
    bounds = body.get("bounds")
    if not bounds and kind != "geo":
        bounds = ICON_BOUNDS
    light_type = str(body.get("light_type") or "").strip().lower()
    if kind == "env_light":
        light_type = light_type or "env"
    elif kind == "light" and light_type not in ("point", "cone", "distant"):
        light_type = "point"
    cone_angle = body.get("cone_angle")
    try:
        cone_angle_f = float(cone_angle) if cone_angle is not None else 30.0
    except (TypeError, ValueError):
        cone_angle_f = 30.0

    # Proxy: prefer explicit body, else preserve previous beauty mesh across Refresh.
    proxy_mode = normalize_proxy_mode(body.get("proxy_mode", (prev or {}).get("proxy_mode", "mask")))
    proxy = None
    if "proxy" in body:
        proxy = normalize_proxy_meta(body.get("proxy")) if proxy_mode == "mesh" else None
    elif prev and prev.get("proxy_mode") == "mesh" and prev.get("proxy"):
        proxy_mode = "mesh"
        proxy = normalize_proxy_meta(prev.get("proxy"))
    if proxy_mode != "mesh":
        proxy = None

    out: dict[str, Any] = {
        "id": oid,
        "name": str(body.get("name") or oid),
        "layer": int(body.get("layer") if body.get("layer") is not None else 0),
        "visible": bool(body.get("visible", True)),
        "trs": normalize_trs(body.get("trs")),
        "bounds": normalize_bounds(bounds),
        "td_path": td_path,
        "kind": kind,
        "op_type": str(body.get("op_type") or ""),
        "proxy_mode": proxy_mode,
        "proxy": proxy,
    }
    if kind in ("light", "env_light"):
        out["light_type"] = light_type or ("env" if kind == "env_light" else "point")
        out["cone_angle"] = cone_angle_f
    return out


class RenderStore:
    def __init__(self) -> None:
        self.state: dict[str, Any] = empty_render_state()
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self._plate_fp: str = ""
        # True when the last set_scene was a no-op (identical plate content).
        self.last_scene_noop: bool = False
        # Low-rate JPEG preview (not part of JSON snapshot / undo)
        self.preview_jpeg: bytes | None = None
        self.preview_path: str = ""
        self.preview_etag: str = ""
        self.preview_pending: bool = False
        self.preview_pending_at: float = 0.0
        self.preview_updated_at: float = 0.0

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)

    def request_preview(self, path: str, *, now: float | None = None) -> bool:
        """Mark a single-flight preview kick. Returns True if a new kick should fire."""
        path = str(path or "").strip()
        if not path:
            return False
        t = time.time() if now is None else now
        if self.preview_pending:
            age = t - float(self.preview_pending_at or 0.0)
            if age < PREVIEW_PENDING_TIMEOUT_S:
                return False
        self.preview_pending = True
        self.preview_pending_at = t
        self.preview_path = path
        return True

    def put_preview(self, jpeg: bytes, path: str = "", *, now: float | None = None) -> dict[str, Any]:
        raw = bytes(jpeg or b"")
        t = time.time() if now is None else now
        self.preview_jpeg = raw if raw else None
        if path:
            self.preview_path = str(path)
        self.preview_etag = hashlib.sha1(raw).hexdigest() if raw else ""
        self.preview_updated_at = t
        self.preview_pending = False
        return {
            "ok": True,
            "path": self.preview_path,
            "etag": self.preview_etag,
            "bytes": len(raw),
        }

    def preview_meta(self) -> dict[str, Any]:
        return {
            "path": self.preview_path,
            "etag": self.preview_etag,
            "pending": self.preview_pending,
            "updated_at": self.preview_updated_at,
            "bytes": len(self.preview_jpeg) if self.preview_jpeg else 0,
        }

    def set_tops(self, tops: list[dict[str, Any]]) -> dict[str, Any]:
        cleaned = []
        for t in tops or []:
            if not isinstance(t, dict):
                continue
            path = str(t.get("path") or "")
            if not path:
                continue
            cleaned.append({"path": path, "name": str(t.get("name") or path.rsplit("/", 1)[-1])})
        self.state["tops"] = cleaned
        return self.snapshot()

    def set_status(self, status: str) -> dict[str, Any]:
        self.state["status"] = str(status or "")
        return self.snapshot()

    def set_scene(self, body: dict[str, Any]) -> dict[str, Any]:
        path = str(body.get("render_path") or body.get("path") or "")
        raw_objs = body.get("objects") or []
        if isinstance(raw_objs, dict):
            raw_list = list(raw_objs.values())
        else:
            raw_list = list(raw_objs)
        prev_objs = self.state.get("objects") or {}
        objects: dict[str, Any] = {}
        counts = {"geo": 0, "light": 0, "camera": 0}
        truncated = False
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            if len(objects) >= MAX_RENDER_OBJECTS:
                truncated = True
                break
            # Stable id before normalize so we can look up previous proxy
            td_path = str(item.get("td_path") or "")
            oid = str(item.get("id") or "") or (_stable_id(td_path) if td_path else "")
            prev = prev_objs.get(oid) if oid else None
            obj = normalize_plate_object(item, prev=prev if isinstance(prev, dict) else None)
            objects[obj["id"]] = obj
            k = obj["kind"]
            if k == "geo":
                counts["geo"] += 1
            elif k in ("light", "env_light"):
                counts["light"] += 1
            elif k == "camera":
                counts["camera"] += 1
        status = f"{counts['geo']} geos · {counts['light']} lights · {counts['camera']} cameras"
        if truncated:
            status += f" (capped at {MAX_RENDER_OBJECTS})"
        new_fp = plate_content_fingerprint(objects, path)
        cur_path = str(self.state.get("render_path") or "")
        cur_fp = plate_content_fingerprint(self.state.get("objects") or {}, cur_path)
        # No-op when plate content matches what's already in the store (incl. after
        # live TRS patches) — keeps selection, undo, and object identity.
        if new_fp == cur_fp and path == cur_path:
            self.last_scene_noop = True
            self._plate_fp = new_fp
            if status != str(self.state.get("status") or ""):
                self.state["status"] = status
            return self.snapshot()
        self.last_scene_noop = False
        prev_sel = list(self.state.get("selection") or [])
        self.state["render_path"] = path
        self.state["objects"] = objects
        # Preserve UI selection across Refresh for IDs that still exist.
        self.state["selection"] = [i for i in prev_sel if i in objects]
        self.state["counts"] = counts
        self.state["status"] = status
        self._plate_fp = new_fp
        self._undo.clear()
        self._redo.clear()
        return self.snapshot()

    def set_selection(self, ids: list[str]) -> None:
        known = self.state["objects"]
        self.state["selection"] = [i for i in ids if i in known]

    def mesh_proxy_count(self) -> int:
        n = 0
        for o in self.state["objects"].values():
            if o.get("proxy_mode") == "mesh" and o.get("proxy"):
                n += 1
        return n

    def set_proxy_meta(self, oid: str, meta: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        obj = self.state["objects"].get(oid)
        if obj is None:
            return None
        if meta is None:
            obj["proxy_mode"] = "mask"
            obj["proxy"] = None
        else:
            obj["proxy_mode"] = "mesh"
            obj["proxy"] = normalize_proxy_meta(meta)
        return copy.deepcopy(obj)

    def _push_undo(self) -> None:
        self._undo.append(copy.deepcopy(self.state))
        self._redo.clear()
        if len(self._undo) > 64:
            self._undo.pop(0)

    def apply_trs_delta(self, oid: str, trs: dict[str, Any]) -> Optional[dict[str, Any]]:
        if oid not in self.state["objects"]:
            return None
        self.state["objects"][oid]["trs"] = normalize_trs(trs)
        return copy.deepcopy(self.state["objects"][oid])

    def patch_trs(self, oid: str, trs: dict[str, Any], *, undoable: bool = True) -> dict[str, Any]:
        if oid not in self.state["objects"]:
            raise KeyError(oid)
        if undoable:
            self._push_undo()
        self.state["objects"][oid]["trs"] = normalize_trs(trs)
        return copy.deepcopy(self.state["objects"][oid])

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self.state))
        self.state = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self.state))
        self.state = self._redo.pop()
        return True
