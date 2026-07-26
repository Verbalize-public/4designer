"""Unit tests for orphan prune debounce helper (no TD)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "td"))

from orphan_debounce import orphan_ready_to_prune  # noqa: E402


class TestOrphanDebounce(unittest.TestCase):
    def test_dwell_before_prune(self):
        suspects: dict[str, float] = {}
        self.assertFalse(
            orphan_ready_to_prune(suspects, "a", missing=True, now=1.0, dwell_s=0.75)
        )
        self.assertIn("a", suspects)
        self.assertFalse(
            orphan_ready_to_prune(suspects, "a", missing=True, now=1.5, dwell_s=0.75)
        )
        self.assertTrue(
            orphan_ready_to_prune(suspects, "a", missing=True, now=1.76, dwell_s=0.75)
        )

    def test_resolved_clears(self):
        suspects = {"a": 1.0}
        self.assertFalse(
            orphan_ready_to_prune(suspects, "a", missing=False, now=2.0, dwell_s=0.75)
        )
        self.assertNotIn("a", suspects)


if __name__ == "__main__":
    unittest.main()
