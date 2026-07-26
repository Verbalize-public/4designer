"""v1 stabilization regressions: undo isolation, destroy idempotency, rekey SHM, preview HTTP."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from fourdesigner_daemon import app as app_mod
from fourdesigner_daemon.render_store import RenderStore
from fourdesigner_daemon.state import StateStore
from fourdesigner_daemon.workspace import WorkspaceRegistry


class TestUndoIsolation(unittest.TestCase):
    def test_marshal_and_render_undo_independent(self):
        marshal = StateStore()
        render = RenderStore()
        marshal.register_object(
            {
                "id": "m1",
                "name": "m",
                "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
            }
        )
        render.set_scene(
            {
                "render_path": "/r",
                "objects": [
                    {
                        "id": "r1",
                        "td_path": "/g",
                        "kind": "geo",
                        "trs": {"t": [0, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]},
                    }
                ],
            }
        )
        marshal.patch_object("m1", {"trs": {"t": [5, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]}})
        render.patch_trs("r1", {"t": [9, 0, 0], "r": [0, 0, 0], "s": [1, 1, 1]})
        self.assertTrue(marshal.undo())
        self.assertEqual(marshal.state["objects"]["m1"]["trs"]["t"][0], 0.0)
        self.assertEqual(render.state["objects"]["r1"]["trs"]["t"][0], 9.0)
        self.assertTrue(render.undo())
        self.assertEqual(render.state["objects"]["r1"]["trs"]["t"][0], 0.0)
        self.assertEqual(marshal.state["objects"]["m1"]["trs"]["t"][0], 0.0)


class TestPendingDestroyIdempotent(unittest.TestCase):
    def setUp(self):
        import os

        self._prev = os.environ.get("FOURDESIGNER_SHM")
        os.environ["FOURDESIGNER_SHM"] = "0"
        app_mod.registry.clear()
        self.w = app_mod.registry.ensure("ws-idem")
        self.client = TestClient(app_mod.app)
        self._send = patch.object(app_mod.hub, "send_td", new=AsyncMock())
        self._send.start()
        self._proxy = patch.object(app_mod.persistence, "delete_proxy_file")
        self._proxy.start()

    def tearDown(self):
        import os

        self._send.stop()
        self._proxy.stop()
        app_mod.registry.clear()
        if self._prev is None:
            os.environ.pop("FOURDESIGNER_SHM", None)
        else:
            os.environ["FOURDESIGNER_SHM"] = self._prev

    def test_double_destroy_flag_does_not_double_enqueue(self):
        hdr = {"X-Workspace-Id": "ws-idem"}
        self.client.post(
            "/api/objects/register",
            json={"id": "x", "name": "m", "td_path": "/p/m"},
            headers=hdr,
        )
        # Re-register same id then destroy twice should not enqueue twice after first gone.
        r1 = self.client.delete("/api/objects/x?destroy_td=true", headers=hdr)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(self.w.pending_destroys), 1)
        # Manually re-add object and destroy again with same id already pending
        self.w.store.register_object({"id": "x", "name": "m", "td_path": "/p/m"})
        r2 = self.client.delete("/api/objects/x?destroy_td=true", headers=hdr)
        self.assertEqual(r2.status_code, 200)
        ids = [d["id"] for d in self.w.pending_destroys]
        self.assertEqual(ids.count("x"), 1)


class TestRekeyShmNoLeak(unittest.TestCase):
    def test_collision_rekey_keeps_original_shm(self):
        from fourdesigner_daemon.shm_buf import SharedTrsBuffer

        reg = WorkspaceRegistry()
        ws1 = MagicMock()
        ws2 = MagicMock()
        w1, _ = reg.bind_td(ws1, "same-id", project_name="a.toe")
        raw = bytearray(0)
        w1.shm = SharedTrsBuffer.from_bytes(raw)
        name1 = w1.shm.name
        w2, rekey = reg.bind_td(ws2, "same-id", project_name="b.toe")
        self.assertIsNotNone(rekey)
        # Original workspace keeps its buffer; rekeyed workspace starts without stealing it.
        self.assertIs(reg.get("same-id").shm, w1.shm)
        self.assertEqual(reg.get("same-id").shm.name, name1)
        self.assertIsNone(w2.shm)
        self.assertIsNot(w2, w1)


class TestPreviewHttpEtag(unittest.TestCase):
    def setUp(self):
        app_mod.registry.clear()
        self.w = app_mod.registry.ensure("ws-prev")
        self.client = TestClient(app_mod.app)
        self.hdr = {"X-Workspace-Id": "ws-prev"}

    def tearDown(self):
        app_mod.registry.clear()

    def test_preview_304_and_single_flight_via_api(self):
        jpeg = b"\xff\xd8\xff\xe0fake"
        put = self.client.put(
            "/api/render/preview?path=/project1/r1",
            content=jpeg,
            headers=self.hdr,
        )
        self.assertEqual(put.status_code, 200)
        etag = put.json()["etag"]
        r = self.client.get(
            "/api/render/preview",
            headers={**self.hdr, "If-None-Match": f'"{etag}"'},
        )
        self.assertEqual(r.status_code, 304)
        # Concurrent request_preview: second while pending is not kicked
        a = self.client.post(
            "/api/render/preview/request",
            json={"path": "/project1/r1"},
            headers=self.hdr,
        )
        self.assertTrue(a.json().get("kicked"))
        b = self.client.post(
            "/api/render/preview/request",
            json={"path": "/project1/r1"},
            headers=self.hdr,
        )
        self.assertFalse(b.json().get("kicked"))


class TestBindOrExitCode(unittest.TestCase):
    def test_port_in_use_exit_constant(self):
        from fourdesigner_daemon.__main__ import PORT_IN_USE_EXIT

        self.assertEqual(PORT_IN_USE_EXIT, 1)


class TestPostWorkspace(unittest.TestCase):
    def setUp(self):
        app_mod.registry.clear()
        self.client = TestClient(app_mod.app)

    def tearDown(self):
        app_mod.registry.clear()

    def test_post_creates_workspace(self):
        r = self.client.post(
            "/api/workspaces",
            json={"id": "e2e-ws", "project_name": "fixture.toe"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], "e2e-ws")
        self.assertIsNotNone(app_mod.registry.get("e2e-ws"))


class TestImportSmoke(unittest.TestCase):
    def test_app_factory_imports(self):
        self.assertTrue(hasattr(app_mod.app, "router"))
        self.assertLess(Path(app_mod.__file__).stat().st_size, 8_000)


if __name__ == "__main__":
    unittest.main()
