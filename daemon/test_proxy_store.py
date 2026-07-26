"""Unit tests for proxy store + mask reject + write_glb."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repository root
TD = ROOT / "td"
sys.path.insert(0, str(ROOT / "daemon") if False else str(Path(__file__).resolve().parent))
sys.path.insert(0, str(TD))

# Ensure daemon package importable when cwd is daemon/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fourdesigner_daemon import persistence  # noqa: E402
from fourdesigner_daemon.state import StateStore  # noqa: E402
import proxy_mesh as pm  # noqa: E402


class TestProxyMesh(unittest.TestCase):
    def test_write_glb_magic(self):
        pts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        tris = [(0, 1, 2)]
        data = pm.write_glb(pts, tris)
        self.assertTrue(data.startswith(b"glTF"))
        self.assertGreater(len(data), 12)

    def test_decimate(self):
        pts = [(float(i), 0, 0) for i in range(100)]
        tris = [(i, i + 1, i + 2) for i in range(0, 97, 3)]
        p2, t2 = pm.decimate_mesh(pts, tris, max_verts=10, max_tris=5)
        self.assertLessEqual(len(p2), 10)
        self.assertLessEqual(len(t2), 5)

    def test_tris_from_vert_pindexes_quad(self):
        # One quad → two tris
        tris = pm.tris_from_vert_pindexes([[0, 1, 2, 3]])
        self.assertEqual(tris, [(0, 1, 2), (0, 2, 3)])


class TestProxyStore(unittest.TestCase):
    def setUp(self):
        self.store = StateStore()
        self.slug = "_test_proxy"
        persistence.ensure_dirs()

    def tearDown(self):
        for oid in list(self.store.state["objects"].keys()):
            persistence.delete_proxy_file(self.slug, oid)

    def test_register_default_mask(self):
        obj = self.store.register_object({"id": "a", "name": "a", "layer": 0})
        self.assertEqual(obj["proxy_mode"], "mask")
        self.assertIsNone(obj.get("proxy"))

    def test_mode_to_mask_clears_proxy(self):
        self.store.register_object({"id": "b", "name": "b", "proxy_mode": "mesh"})
        self.store.set_proxy_meta(
            "b",
            {
                "format": "glb",
                "url": "/api/objects/b/proxy.glb",
                "fingerprint": "x",
                "verts": 1,
                "tris": 1,
                "rev": 1,
            },
        )
        self.assertIsNotNone(self.store.state["objects"]["b"]["proxy"])
        self.store.set_proxy_mode_quiet("b", "mask")
        self.assertEqual(self.store.state["objects"]["b"]["proxy_mode"], "mask")
        self.assertIsNone(self.store.state["objects"]["b"]["proxy"])

    def test_put_bytes_roundtrip(self):
        self.store.register_object({"id": "c", "name": "c", "proxy_mode": "mesh"})
        glb = pm.write_glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
        persistence.write_proxy_bytes(self.slug, "c", glb)
        raw = persistence.read_proxy_bytes(self.slug, "c")
        self.assertEqual(raw[:4], b"glTF")

    def test_mask_set_proxy_meta_ignored(self):
        self.store.register_object({"id": "d", "name": "d", "proxy_mode": "mask"})
        self.store.set_proxy_meta(
            "d",
            {"format": "glb", "url": "/x", "fingerprint": "", "verts": 0, "tris": 0, "rev": 1},
        )
        self.assertIsNone(self.store.state["objects"]["d"]["proxy"])


if __name__ == "__main__":
    unittest.main()
