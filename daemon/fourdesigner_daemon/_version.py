"""Read package version from the repository VERSION file."""

from __future__ import annotations

from pathlib import Path


def _read_version() -> str:
    # fourdesigner_daemon/ → daemon/ → 4designer/VERSION
    root = Path(__file__).resolve().parent.parent.parent
    version_file = root / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text.splitlines()[0].strip()
    except OSError:
        pass
    return "1.0.0"


__version__ = _read_version()
