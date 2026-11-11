"""FastAPI entry point. Run from repo root: uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import errors, routes
from .config import Settings, get_settings
from .services.container import Container

DESCRIPTION = """
Stock Insight 本机后端。数据只来自免费公开源（同花顺、东方财富、Yahoo），日线增量存入本地 SQLite。

每个响应都带 `meta`：`source` 来源、`as_of` 数据日期、`fetched_at` 取数时间、`freshness`
（live 实时 / closed 已收盘 / provisional 盘中合成 / fallback 备用源 / cached 本地缓存）以及 `note` 提示。
错误统一为 `{"error": {"category", "message", "detail"}}`，`message` 为中文。
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "container", None) is None:
            app.state.container = Container(settings)
        yield
        app.state.container.close()

    app = FastAPI(title="Stock Insight API", version="0.2.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.container = container
    errors.install(app)
    app.include_router(routes.router)

    dist = settings.frontend_dist
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
