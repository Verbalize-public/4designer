"""Unit tests for RenderStore."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fourdesigner_daemon.render_store import (  # noqa: E402
    PREVIEW_PENDING_TIMEOUT_S,
    RenderStore,
)


class TestRenderStore(unittest.TestCase):
    def test_set_scene_and_counts(self):
        s = RenderStore()
        snap = s.set_scene(
            {
                "render_path": "/project1/render1",
                "objects": [
                    {"td_path": "/project1/geo1", "name": "geo1", "kind": "geo"},
                    {"td_path": "/project1/light1", "name": "light1", "kind": "light"},
                    {"td_path": "/project1/cam1", "name": "cam1", "kind": "camera"},
                ],
            }
        )
        self.assertEqual(snap["counts"]["geo"], 1)
        self.assertEqual(snap["counts"]["light"], 1)
        self.assertEqual(snap["counts"]["camera"], 1)
        self.assertEqual(len(snap["objects"]), 3)

    def test_patch_undo(self):
        s = RenderStore()
        s.set_scene(
            {
                "objects": [
                    {
                        "id": "a",
                        "td_path": "/p/g",
                        "name": "g",
                        "kind": "geo",
                        "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                    }
                ]
            }
        )
        s.patch_trs("a", {"t": [2, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]})
        self.assertEqual(s.state["objects"]["a"]["trs"]["t"][0], 2.0)
        self.assertTrue(s.undo())
        self.assertEqual(s.state["objects"]["a"]["trs"]["t"][0], 0.0)
        self.assertTrue(s.redo())
        self.assertEqual(s.state["objects"]["a"]["trs"]["t"][0], 2.0)

    def test_delta_not_undoable(self):
        s = RenderStore()
        s.set_scene(
            {
                "objects": [
                    {
                        "id": "a",
                        "td_path": "/p/g",
                        "kind": "geo",
                        "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                    }
                ]
            }
        )
        s.apply_trs_delta("a", {"t": [3, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]})
        self.assertFalse(s.undo())

    def test_light_cue_fields(self):
        s = RenderStore()
        snap = s.set_scene(
            {
                "objects": [
                    {
                        "td_path": "/p/l",
                        "kind": "light",
                        "light_type": "cone",
                        "cone_angle": 45,
                    }
                ]
            }
        )
        obj = next(iter(snap["objects"].values()))
        self.assertEqual(obj["light_type"], "cone")
        self.assertEqual(obj["cone_angle"], 45.0)

    def test_preserve_proxy_across_refresh(self):
        s = RenderStore()
        s.set_scene({"objects": [{"td_path": "/p/g", "kind": "geo", "name": "g"}]})
        oid = next(iter(s.state["objects"].keys()))
        s.set_proxy_meta(
            oid,
            {
                "format": "glb",
                "url": f"/api/render/objects/{oid}/proxy.glb",
                "fingerprint": "fp1",
                "verts": 10,
                "tris": 5,
                "rev": 1,
            },
        )
        s.set_scene(
            {
                "objects": [
                    {"td_path": "/p/g", "kind": "geo", "name": "g", "proxy_mode": "mask"}
                ]
            }
        )
        obj = s.state["objects"][oid]
        self.assertEqual(obj["proxy_mode"], "mesh")
        self.assertEqual(obj["proxy"]["fingerprint"], "fp1")

    def test_set_scene_preserves_selection(self):
        s = RenderStore()
        s.set_scene(
            {
                "render_path": "/r",
                "objects": [
                    {
                        "td_path": "/p/g",
                        "kind": "geo",
                        "name": "g",
                        "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                    }
                ],
            }
        )
        oid = next(iter(s.state["objects"].keys()))
        s.set_selection([oid])
        self.assertEqual(s.state["selection"], [oid])
        # Changed TRS → apply, but keep selection
        s.set_scene(
            {
                "render_path": "/r",
                "objects": [
                    {
                        "td_path": "/p/g",
                        "kind": "geo",
                        "name": "g",
                        "trs": {"t": [1, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                    }
                ],
            }
        )
        self.assertFalse(s.last_scene_noop)
        self.assertEqual(s.state["selection"], [oid])

    def test_set_scene_noop_when_unchanged(self):
        s = RenderStore()
        body = {
            "render_path": "/r",
            "objects": [
                {
                    "td_path": "/p/g",
                    "kind": "geo",
                    "name": "g",
                    "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                }
            ],
        }
        s.set_scene(body)
        self.assertFalse(s.last_scene_noop)
        oid = next(iter(s.state["objects"].keys()))
        s.set_selection([oid])
        # Identical re-snapshot → no-op (selection + undo kept)
        s.set_scene(body)
        self.assertTrue(s.last_scene_noop)
        self.assertEqual(s.state["selection"], [oid])
        # After a live TRS patch, refreshing the same TD pose is still a no-op
        s.patch_trs(oid, {"t": [2, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]})
        undo_len = len(s._undo)
        cur_objs = list(s.snapshot()["objects"].values())
        s.set_scene({"render_path": "/r", "objects": cur_objs})
        self.assertTrue(s.last_scene_noop)
        self.assertEqual(s.state["selection"], [oid])
        self.assertEqual(len(s._undo), undo_len)

    def test_preview_put_and_etag(self):
        s = RenderStore()
        meta = s.put_preview(b"\xff\xd8fakejpeg", "/project1/r1", now=100.0)
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["bytes"], 10)
        self.assertEqual(s.preview_path, "/project1/r1")
        self.assertEqual(s.preview_etag, meta["etag"])
        self.assertFalse(s.preview_pending)
        self.assertEqual(s.preview_jpeg, b"\xff\xd8fakejpeg")

    def test_preview_single_flight(self):
        s = RenderStore()
        self.assertTrue(s.request_preview("/project1/r1", now=1.0))
        self.assertTrue(s.preview_pending)
        # Duplicate while pending → no kick
        self.assertFalse(s.request_preview("/project1/r1", now=1.5))
        # After timeout → kick again
        self.assertTrue(
            s.request_preview("/project1/r1", now=1.0 + PREVIEW_PENDING_TIMEOUT_S + 0.01)
        )
        s.put_preview(b"abc", "/project1/r1", now=10.0)
        self.assertFalse(s.preview_pending)
        # After PUT, next request kicks
        self.assertTrue(s.request_preview("/project1/r1", now=11.0))

    def test_preview_request_requires_path(self):
        s = RenderStore()
        self.assertFalse(s.request_preview(""))
        self.assertFalse(s.preview_pending)


if __name__ == "__main__":
    unittest.main()
