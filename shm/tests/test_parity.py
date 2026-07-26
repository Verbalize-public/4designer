"""Assert daemon + td re-exports share the same wire-format constants."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAEMON_DIR = ROOT.parent / "daemon"
if str(DAEMON_DIR) not in sys.path:
    sys.path.insert(0, str(DAEMON_DIR))

TD_DIR = ROOT.parent / "td"
if str(TD_DIR) not in sys.path:
    sys.path.insert(0, str(TD_DIR))


class TestShmParity(unittest.TestCase):
    def test_constants_match(self):
        import fourdesigner_shm.shm_buf as shared
        from fourdesigner_daemon import shm_buf as daemon

        # td/shm_buf.py is a re-export module (not a package)
        import importlib

        td = importlib.import_module("shm_buf")

        for attr in (
            "MAGIC",
            "VERSION",
            "TOTAL_SIZE",
            "SLOT_COUNT",
            "CMD_CAPACITY",
            "CMD_DESTROY",
            "CMD_SNAPSHOT",
            "CMD_PREVIEW",
            "CMD_LIST_TOPS",
            "CMD_COOK_PROXIES",
            "CMD_REFRESH_PROXY",
        ):
            self.assertEqual(getattr(shared, attr), getattr(daemon, attr), attr)
            self.assertEqual(getattr(shared, attr), getattr(td, attr), attr)

    def test_shm_name_stable(self):
        import fourdesigner_shm.shm_buf as shared

        self.assertTrue(shared.shm_name("abc").startswith("fourdesigner_"))


if __name__ == "__main__":
    unittest.main()
