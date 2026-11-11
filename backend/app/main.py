"""FastAPI entry point. Run from repo root: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import health
from .config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Insight API", version="0.1.0")
    app.include_router(health.router)

    dist = get_settings().frontend_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="接口不存在")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
