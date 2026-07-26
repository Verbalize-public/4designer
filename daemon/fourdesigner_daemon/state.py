"""In-memory source of truth for 4designer objects, layers, undo."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Callable, Optional

LAYER_PALETTE = [
    "#4aa3ff",
    "#f0a020",
    "#3ecf8e",
    "#e85d75",
    "#9b7bff",
    "#2ec4b6",
    "#ff6b6b",
    "#c9d1d9",
]

DEFAULT_BOUNDS = {
    "min": [-0.5, -0.5, -0.5],
    "max": [0.5, 0.5, 0.5],
}

DEFAULT_TRS = {
    "t": [0.0, 0.0, 0.0],
    "r": [0.0, 0.0, 0.0],
    "s": [1.0, 1.0, 1.0],
}


def _vec3(v: Any, fallback: list[float]) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return list(fallback)
    return [float(v[0]), float(v[1]), float(v[2])]


def normalize_trs(trs: Optional[dict[str, Any]] = None) -> dict[str, list[float]]:
    src = trs or {}
    return {
        "t": _vec3(src.get("t"), DEFAULT_TRS["t"]),
        "r": _vec3(src.get("r"), DEFAULT_TRS["r"]),
        "s": _vec3(src.get("s"), DEFAULT_TRS["s"]),
    }


def normalize_bounds(bounds: Optional[dict[str, Any]] = None) -> dict[str, list[float]]:
    src = bounds or {}
    return {
        "min": _vec3(src.get("min"), DEFAULT_BOUNDS["min"]),
        "max": _vec3(src.get("max"), DEFAULT_BOUNDS["max"]),
    }


def normalize_proxy_mode(mode: Any) -> str:
    m = str(mode or "mask").strip().lower()
    return "mesh" if m == "mesh" else "mask"


def normalize_proxy_meta(proxy: Any) -> Optional[dict[str, Any]]:
    if not proxy or not isinstance(proxy, dict):
        return None
    url = str(proxy.get("url") or "")
    if not url:
        return None
    return {
        "format": str(proxy.get("format") or "glb"),
        "url": url,
        "fingerprint": str(proxy.get("fingerprint") or ""),
        "verts": int(proxy.get("verts") or 0),
        "tris": int(proxy.get("tris") or 0),
        "rev": int(proxy.get("rev") or 1),
    }


def default_layers() -> dict[str, dict[str, Any]]:
    return {
        "0": {
            "name": "Universe 0",
            "visible": True,
            "color": LAYER_PALETTE[0],
        }
    }


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "layers": default_layers(),
        "objects": {},
        "selection": [],
    }


class StateStore:
    """Mutable SOT with undo stack for commit-style mutations."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = empty_state()
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []
        self.td_connected: bool = False
        self.td_seen_at: float = 0.0
        self.slug: str = "default"

    def on_change(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    def snapshot(self) -> dict[str, Any]:
        snap = copy.deepcopy(self.state)
        snap["td_connected"] = self.td_connected
        snap["slug"] = self.slug
        return snap

    def load_state(self, data: dict[str, Any]) -> None:
        layers = data.get("layers")
        if not isinstance(layers, dict) or not layers:
            layers = default_layers()
        objects_in = data.get("objects")
        if not isinstance(objects_in, dict):
            objects_in = {}
        objects: dict[str, Any] = {}
        for oid, raw in objects_in.items():
            if not isinstance(raw, dict):
                continue
            mode = normalize_proxy_mode(raw.get("proxy_mode", "mask"))
            objects[str(oid)] = {
                "id": str(raw.get("id") or oid),
                "name": str(raw.get("name") or oid),
                "layer": int(raw.get("layer", 0)),
                "visible": bool(raw.get("visible", True)),
                "trs": normalize_trs(raw.get("trs")),
                "bounds": normalize_bounds(raw.get("bounds")),
                "td_path": str(raw.get("td_path") or ""),
                "proxy_mode": mode,
                "proxy": normalize_proxy_meta(raw.get("proxy")) if mode == "mesh" else None,
            }
        selection = data.get("selection")
        if not isinstance(selection, list):
            selection = []
        self.state = {
            "schema_version": int(data.get("schema_version") or 1),
            "layers": copy.deepcopy(layers),
            "objects": objects,
            "selection": [str(x) for x in selection],
        }
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def clear(self) -> None:
        self._push_undo()
        self.state = empty_state()
        self._redo.clear()
        self._notify()

    def _push_undo(self) -> None:
        self._undo.append(copy.deepcopy(self.state))
        if len(self._undo) > 100:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self.state))
        self.state = self._undo.pop()
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self.state))
        self.state = self._redo.pop()
        self._notify()
        return True

    def ensure_layer(self, layer: int) -> None:
        key = str(int(layer))
        if key in self.state["layers"]:
            return
        idx = int(layer) % len(LAYER_PALETTE)
        self.state["layers"][key] = {
            "name": f"Universe {key}",
            "visible": True,
            "color": LAYER_PALETTE[idx],
        }

    def register_object(self, body: dict[str, Any]) -> dict[str, Any]:
        oid = str(body.get("id") or uuid.uuid4())
        layer = int(body.get("layer", 0))
        self.ensure_layer(layer)
        mode = normalize_proxy_mode(body.get("proxy_mode", "mask"))
        obj = {
            "id": oid,
            "name": str(body.get("name") or oid),
            "layer": layer,
            "visible": bool(body.get("visible", True)),
            "trs": normalize_trs(body.get("trs")),
            "bounds": normalize_bounds(body.get("bounds")),
            "td_path": str(body.get("td_path") or ""),
            "proxy_mode": mode,
            "proxy": normalize_proxy_meta(body.get("proxy")) if mode == "mesh" else None,
        }
        # Register is idempotent by id; not undoable (lifecycle).
        self.state["objects"][oid] = obj
        self._notify()
        return copy.deepcopy(obj)

    def unregister_object(self, oid: str) -> bool:
        if oid not in self.state["objects"]:
            return False
        del self.state["objects"][oid]
        self.state["selection"] = [s for s in self.state["selection"] if s != oid]
        self._notify()
        return True

    def set_bounds_quiet(self, oid: str, bounds: dict[str, Any]) -> Optional[dict[str, Any]]:
        if oid not in self.state["objects"]:
            return None
        self.state["objects"][oid]["bounds"] = normalize_bounds(bounds)
        self._notify()
        return copy.deepcopy(self.state["objects"][oid])

    def set_proxy_mode_quiet(self, oid: str, mode: str) -> Optional[dict[str, Any]]:
        if oid not in self.state["objects"]:
            return None
        m = normalize_proxy_mode(mode)
        obj = self.state["objects"][oid]
        obj["proxy_mode"] = m
        if m == "mask":
            obj["proxy"] = None
        self._notify()
        return copy.deepcopy(obj)

    def set_proxy_meta(
        self, oid: str, meta: Optional[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        if oid not in self.state["objects"]:
            return None
        obj = self.state["objects"][oid]
        if obj.get("proxy_mode") != "mesh":
            obj["proxy"] = None
        else:
            obj["proxy"] = normalize_proxy_meta(meta)
        self._notify()
        return copy.deepcopy(obj)

    def mesh_proxy_count(self) -> int:
        n = 0
        for o in self.state["objects"].values():
            if o.get("proxy_mode") == "mesh" and o.get("proxy"):
                n += 1
        return n

    def patch_object(
        self,
        oid: str,
        body: dict[str, Any],
        *,
        undoable: bool = True,
    ) -> dict[str, Any]:
        if oid not in self.state["objects"]:
            raise KeyError(oid)
        if undoable:
            self._push_undo()
        obj = self.state["objects"][oid]
        if "name" in body and body["name"] is not None:
            obj["name"] = str(body["name"])
        if "layer" in body and body["layer"] is not None:
            layer = int(body["layer"])
            self.ensure_layer(layer)
            obj["layer"] = layer
        if "visible" in body and body["visible"] is not None:
            obj["visible"] = bool(body["visible"])
        if "trs" in body and body["trs"] is not None:
            obj["trs"] = normalize_trs(body["trs"])
        if "bounds" in body and body["bounds"] is not None:
            obj["bounds"] = normalize_bounds(body["bounds"])
        if "td_path" in body and body["td_path"] is not None:
            obj["td_path"] = str(body["td_path"])
        if "proxy_mode" in body and body["proxy_mode"] is not None:
            m = normalize_proxy_mode(body["proxy_mode"])
            obj["proxy_mode"] = m
            if m == "mask":
                obj["proxy"] = None
        if "proxy" in body:
            if obj.get("proxy_mode") == "mesh":
                obj["proxy"] = normalize_proxy_meta(body["proxy"])
            else:
                obj["proxy"] = None
        self._notify()
        return copy.deepcopy(obj)

    def apply_trs_delta(self, oid: str, trs: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Non-undoable live drag update."""
        if oid not in self.state["objects"]:
            return None
        obj = self.state["objects"][oid]
        obj["trs"] = normalize_trs(trs)
        # Do not notify full listeners for every delta — app broadcasts set_trs.
        return copy.deepcopy(obj)

    def set_selection(self, ids: list[str]) -> None:
        known = set(self.state["objects"].keys())
        self.state["selection"] = [i for i in ids if i in known]
        self._notify()

    def set_layer_visible(self, layer: int, visible: bool) -> dict[str, Any]:
        self._push_undo()
        key = str(int(layer))
        self.ensure_layer(int(layer))
        self.state["layers"][key]["visible"] = bool(visible)
        self._notify()
        return copy.deepcopy(self.state["layers"][key])

    def set_layer_meta(
        self, layer: int, *, name: Optional[str] = None, visible: Optional[bool] = None
    ) -> dict[str, Any]:
        self._push_undo()
        key = str(int(layer))
        self.ensure_layer(int(layer))
        layer_obj = self.state["layers"][key]
        if name is not None:
            layer_obj["name"] = str(name)
        if visible is not None:
            layer_obj["visible"] = bool(visible)
        self._notify()
        return copy.deepcopy(layer_obj)
