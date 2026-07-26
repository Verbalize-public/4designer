"""Daemon SHM wire: transform writes SHM without set_trs to TD."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fourdesigner_daemon import app as app_mod
from fourdesigner_daemon.shm_buf import SLOT_COUNT, SharedTrsBuffer, id_hash


class TestShmWire(unittest.TestCase):
    def setUp(self):
        self._prev_shm_env = os.environ.get("FOURDESIGNER_SHM")
        if "FOURDESIGNER_SHM" in os.environ:
            del os.environ["FOURDESIGNER_SHM"]
        app_mod.registry.clear()
        self.w = app_mod.registry.ensure("test_shm")
        raw = bytearray(0)
        self.buf = SharedTrsBuffer.from_bytes(raw)
        self.w.shm = self.buf
        self.td_msgs: list[dict] = []

        async def capture_td(w, msg):
            self.td_msgs.append(msg)

        self._send_td_patch = patch.object(
            app_mod.hub, "send_td", new=AsyncMock(side_effect=capture_td)
        )
        self._send_td_patch.start()

    def tearDown(self):
        self._send_td_patch.stop()
        app_mod.registry.clear()
        if self._prev_shm_env is None:
            os.environ.pop("FOURDESIGNER_SHM", None)
        else:
            os.environ["FOURDESIGNER_SHM"] = self._prev_shm_env

    def test_emit_set_trs_uses_shm_no_ws(self):
        obj = self.w.store.register_object(
            {
                "id": "a",
                "name": "m",
                "td_path": "/project1/m",
                "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
            }
        )
        obj = self.w.store.apply_trs_delta("a", {"t": [2.5, 0, 0]})
        assert obj is not None
        asyncio.run(app_mod._emit_set_trs(self.w, "a", obj))
        self.assertEqual(self.td_msgs, [])
        last = [0] * SLOT_COUNT
        dirty = self.buf.collect_dirty(last, max_n=8)
        self.assertEqual(len(dirty), 1)
        self.assertEqual(dirty[0].id_hash, id_hash("a"))
        self.assertAlmostEqual(dirty[0].t[0], 2.5, places=4)

    def test_fallback_ws_when_shm_down(self):
        self.w.shm = None
        with patch.dict(os.environ, {"FOURDESIGNER_SHM": "0"}):
            obj = self.w.store.register_object(
                {"id": "b", "name": "m", "td_path": "/project1/m2"}
            )
            asyncio.run(app_mod._emit_set_trs(self.w, "b", obj))
        set_trs = [m for m in self.td_msgs if m.get("type") == "set_trs"]
        self.assertEqual(len(set_trs), 1)

    def test_destroy_pushes_cmd(self):
        self.w.store.register_object(
            {"id": "c", "name": "m", "td_path": "/project1/m3"}
        )
        self.w.pending_destroys.clear()
        from fastapi.testclient import TestClient

        client = TestClient(app_mod.app)
        with patch.object(app_mod.persistence, "delete_proxy_file"):
            r = client.delete(
                "/api/objects/c?destroy_td=true",
                headers={"X-Workspace-Id": "test_shm"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("c", self.w.store.state["objects"])
        cmds = self.buf.pop_cmds(max_n=4)
        self.assertTrue(any(c.type == app_mod.CMD_DESTROY for c in cmds))


if __name__ == "__main__":
    unittest.main()
