"""Mount built frontend or fallback root JSON."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..runtime import FRONTEND_DIST, log


def mount_static(app: FastAPI) -> None:
    if FRONTEND_DIST.exists():
        log.info("frontend dist found: %s", FRONTEND_DIST)
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
    else:
        log.info("frontend dist missing: %s", FRONTEND_DIST)
        log.warning(
            "frontend dist missing — UI unavailable; run npm run build in frontend/"
        )

        @app.get("/")
        def no_ui() -> dict[str, str]:
            return {
                "app": "4designer",
                "note": "frontend not built yet; run npm run build in frontend/",
            }
