"""Rest-space bounds normalize + decimated GLB writer for 4designer proxies.

Pure helpers are unit-testable without TouchDesigner. TD extract lives in
MarshalExt and calls write_glb / decimate_mesh.
"""

from __future__ import annotations

import json
import struct
import time
from typing import Any, Optional

DEFAULT_BOUNDS = {
    "min": [-0.5, -0.5, -0.5],
    "max": [0.5, 0.5, 0.5],
}

MAX_VERTS = 4000
MAX_TRIS = 8000
EXTRACT_BUDGET_S = 0.1


def _vec3(v: Any, fallback: list[float]) -> list[float]:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        # TD Bounds object style: .min.x / .min[0]
        try:
            return [float(v[0]), float(v[1]), float(v[2])]
        except Exception:
            pass
        try:
            return [float(v.x), float(v.y), float(v.z)]
        except Exception:
            return list(fallback)
    return [float(v[0]), float(v[1]), float(v[2])]


def normalize_bounds_obj(b: Any) -> dict[str, list[float]]:
    """Accept dict, TD bounds(), or None → {min,max} float lists."""
    if b is None:
        return {
            "min": list(DEFAULT_BOUNDS["min"]),
            "max": list(DEFAULT_BOUNDS["max"]),
        }
    if isinstance(b, dict):
        return {
            "min": _vec3(b.get("min"), DEFAULT_BOUNDS["min"]),
            "max": _vec3(b.get("max"), DEFAULT_BOUNDS["max"]),
        }
    # TD POP.bounds() — attributes min/max as vectors
    try:
        mn = getattr(b, "min", None)
        mx = getattr(b, "max", None)
        if mn is not None and mx is not None:
            return {"min": _vec3(mn, DEFAULT_BOUNDS["min"]), "max": _vec3(mx, DEFAULT_BOUNDS["max"])}
    except Exception:
        pass
    return {
        "min": list(DEFAULT_BOUNDS["min"]),
        "max": list(DEFAULT_BOUNDS["max"]),
    }


def bounds_fingerprint(bounds: dict[str, list[float]], n_points: int = 0, n_prims: int = 0) -> str:
    mn = bounds["min"]
    mx = bounds["max"]

    def r(x: float) -> float:
        return round(float(x), 4)

    return f"p{n_points}:t{n_prims}:b{r(mn[0])},{r(mn[1])},{r(mn[2])},{r(mx[0])},{r(mx[1])},{r(mx[2])}"


def decimate_mesh(
    points: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
    max_verts: int = MAX_VERTS,
    max_tris: int = MAX_TRIS,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Stride triangles then compact unused verts."""
    if not points or not triangles:
        return [], []
    tris = list(triangles)
    if len(tris) > max_tris:
        step = max(1, len(tris) // max_tris)
        tris = tris[::step][:max_tris]
    used: set[int] = set()
    for a, b, c in tris:
        used.add(a)
        used.add(b)
        used.add(c)
    if len(used) > max_verts:
        # Keep first max_verts of used indices (stable-ish)
        keep = sorted(used)[:max_verts]
        keep_set = set(keep)
        tris = [t for t in tris if t[0] in keep_set and t[1] in keep_set and t[2] in keep_set]
        used = keep_set
    remap: dict[int, int] = {}
    new_pts: list[tuple[float, float, float]] = []
    for i in sorted(used):
        if i < 0 or i >= len(points):
            continue
        remap[i] = len(new_pts)
        new_pts.append(points[i])
    new_tris: list[tuple[int, int, int]] = []
    for a, b, c in tris:
        if a in remap and b in remap and c in remap:
            new_tris.append((remap[a], remap[b], remap[c]))
    return new_pts, new_tris


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def write_glb(
    points: list[tuple[float, float, float]],
    triangles: list[tuple[int, int, int]],
) -> bytes:
    """Minimal GLB: POSITION + triangle indices (no vertex colors)."""
    if not points or not triangles:
        raise ValueError("empty mesh")
    n = len(points)
    pos = bytearray()
    for x, y, z in points:
        pos += struct.pack("<fff", float(x), float(y), float(z))

    use_u32 = n > 65535
    idx_bytes = bytearray()
    for a, b, c in triangles:
        if use_u32:
            idx_bytes += struct.pack("<III", a, b, c)
        else:
            idx_bytes += struct.pack("<HHH", a, b, c)

    bin_blob = bytearray()
    bin_blob += pos
    bin_blob += b"\x00" * _pad4(len(bin_blob))
    idx_ofs = len(bin_blob)
    bin_blob += idx_bytes
    bin_blob += b"\x00" * _pad4(len(bin_blob))

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    min_p = [min(xs), min(ys), min(zs)]
    max_p = [max(xs), max(ys), max(zs)]
    comp_type = 5125 if use_u32 else 5123

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "4designer-proxy"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "proxy"}],
        "meshes": [
            {
                "name": "proxy",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "mode": 4,
                    }
                ],
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": n,
                "type": "VEC3",
                "max": max_p,
                "min": min_p,
            },
            {
                "bufferView": 1,
                "componentType": comp_type,
                "count": len(triangles) * 3,
                "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pos), "target": 34962},
            {
                "buffer": 0,
                "byteOffset": idx_ofs,
                "byteLength": len(idx_bytes),
                "target": 34963,
            },
        ],
        "buffers": [{"byteLength": len(bin_blob)}],
    }
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * _pad4(len(json_bytes))

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total)
    out += struct.pack("<I4s", len(json_bytes), b"JSON")
    out += json_bytes
    out += struct.pack("<I4s", len(bin_blob), b"BIN\x00")
    out += bin_blob
    return bytes(out)


def probe_pop_bounds(pop) -> tuple[dict[str, list[float]], str]:
    """Return (bounds, status_hint). Uses .bounds() then point sample fallback."""
    if pop is None:
        return normalize_bounds_obj(None), "bounds_fallback"
    try:
        b = pop.bounds()
        nb = normalize_bounds_obj(b)
        # Reject degenerate
        if any(abs(nb["max"][i] - nb["min"][i]) > 1e-9 for i in range(3)):
            return nb, "bounds_ok"
    except Exception:
        pass
    # Light point sample
    try:
        t0 = time.perf_counter()
        pts = pop.points("P") if hasattr(pop, "points") else None
        if pts is None:
            return normalize_bounds_obj(None), "bounds_fallback"
        xs: list[float] = []
        ys: list[float] = []
        zs: list[float] = []
        n = 0
        for p in pts:
            if time.perf_counter() - t0 > EXTRACT_BUDGET_S:
                break
            try:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
                zs.append(float(p[2]))
            except Exception:
                try:
                    xs.append(float(p.x))
                    ys.append(float(p.y))
                    zs.append(float(p.z))
                except Exception:
                    continue
            n += 1
            if n >= 2000:
                break
        if not xs:
            return normalize_bounds_obj(None), "bounds_fallback"
        return {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }, "bounds_ok"
    except Exception:
        return normalize_bounds_obj(None), "bounds_fallback"


def tris_from_vert_pindexes(
    prim_pindexes: list[list[int]],
    max_tris: int = MAX_TRIS,
) -> list[tuple[int, int, int]]:
    """Fan-triangulate per-primitive point-index lists (tri / quad / n-gon)."""
    tris: list[tuple[int, int, int]] = []
    for idxs in prim_pindexes:
        if len(idxs) < 3:
            continue
        if len(idxs) == 3:
            tris.append((idxs[0], idxs[1], idxs[2]))
        else:
            # Quad / n-gon fan from first vertex
            for i in range(1, len(idxs) - 1):
                tris.append((idxs[0], idxs[i], idxs[i + 1]))
                if len(tris) >= max_tris * 4:
                    return tris
        if len(tris) >= max_tris * 4:
            break
    return tris


def _parse_popto_vert_table(dat) -> list[list[int]]:
    """Read POP to DAT (extract=vertices) → list of pindex lists per prim.

    Expected columns include ``prim:vindex`` (e.g. ``0:2``) and ``pindex``.
    """
    if dat is None or dat.numRows < 2:
        return []
    hdr = [str(dat[0, c].val).lower() for c in range(dat.numCols)]
    try:
        col_pv = hdr.index("prim:vindex")
        col_pi = hdr.index("pindex")
    except ValueError:
        return []
    by_prim: dict[int, list[tuple[int, int]]] = {}
    for r in range(1, dat.numRows):
        pv = str(dat[r, col_pv].val)
        try:
            prim_s, vert_s = pv.split(":", 1)
            prim_i = int(prim_s)
            vert_i = int(vert_s)
            pindex = int(float(dat[r, col_pi].val))
        except Exception:
            continue
        by_prim.setdefault(prim_i, []).append((vert_i, pindex))
    out: list[list[int]] = []
    for prim_i in sorted(by_prim.keys()):
        verts = sorted(by_prim[prim_i], key=lambda t: t[0])
        out.append([p for _, p in verts])
    return out


def _extract_tris_via_popto_dat(pop, t0: float, budget_s: float) -> Optional[list[list[int]]]:
    """Ephemeral POP to DAT download of vertex→point indices. None = timeout."""
    parent = getattr(pop, "parent", None)
    parent = parent() if callable(parent) else None
    if parent is None:
        return []
    # poptoDAT is a TD global when running inside TouchDesigner
    try:
        create = parent.create
    except Exception:
        return []
    name = "_fd_proxy_vert_extract"
    existing = parent.op(name)
    if existing is not None:
        try:
            existing.destroy()
        except Exception:
            pass
    try:
        # Late-bound OP type — available in TD Python, not in unit tests
        import td  # type: ignore

        dat = parent.create(td.poptoDAT, name)
    except Exception:
        try:
            dat = parent.create(poptoDAT, name)  # type: ignore[name-defined]
        except Exception:
            return []
    try:
        dat.par.pop = pop
        dat.par.extract = "vertices"
        if hasattr(dat.par, "downloadtype"):
            dat.par.downloadtype = "immediate"
        dat.cook(force=True)
        if time.perf_counter() - t0 > budget_s:
            return None
        return _parse_popto_vert_table(dat)
    except Exception:
        return []
    finally:
        try:
            dat.destroy()
        except Exception:
            pass


def extract_pop_triangles(
    pop,
    max_verts: int = MAX_VERTS,
    max_tris: int = MAX_TRIS,
    budget_s: float = EXTRACT_BUDGET_S,
) -> Optional[tuple[list[tuple[float, float, float]], list[tuple[int, int, int]], str]]:
    """Extract P + triangle (or quad→tri) indices from a POP.

    TD 2025: ``prims`` / ``verts`` require an attribute name and do not expose
    the index buffer directly. Topology comes from an ephemeral POP to DAT
    (extract=vertices → ``pindex`` + ``prim:vindex``).

    Returns (points, tris, status) or None on hard failure.
    status: ok | proxy_timeout | proxy_fallback
    """
    if pop is None:
        return None
    t0 = time.perf_counter()
    points: list[tuple[float, float, float]] = []
    try:
        # Immediate download — delayed=True can return stale/wrong buffers
        pts_attr = None
        try:
            pts_attr = pop.points("P")
        except Exception:
            pts_attr = pop.points("P") if hasattr(pop, "points") else None
        if pts_attr is None:
            return [], [], "proxy_fallback"
        for p in pts_attr:
            if time.perf_counter() - t0 > budget_s:
                return None
            try:
                points.append((float(p[0]), float(p[1]), float(p[2])))
            except Exception:
                points.append((float(p.x), float(p.y), float(p.z)))
            if len(points) > max_verts * 4:
                break
    except Exception:
        return [], [], "proxy_fallback"

    if not points:
        return [], [], "proxy_fallback"

    prim_lists = _extract_tris_via_popto_dat(pop, t0, budget_s)
    if prim_lists is None:
        return None
    tris = tris_from_vert_pindexes(prim_lists, max_tris=max_tris)

    if not tris:
        return points, [], "proxy_fallback"

    pts2, tris2 = decimate_mesh(points, tris, max_verts=max_verts, max_tris=max_tris)
    if not pts2 or not tris2:
        return points, [], "proxy_fallback"
    status = "ok"
    if time.perf_counter() - t0 > budget_s:
        status = "proxy_timeout"
    return pts2, tris2, status
