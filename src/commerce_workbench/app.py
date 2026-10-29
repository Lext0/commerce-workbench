from contextlib import asynccontextmanager
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commerce_workbench import __version__
from commerce_workbench.config import Settings
from commerce_workbench.database import Database, RevisionConflict
from commerce_workbench.schemas import WorkspaceUpdate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        yield

    app = FastAPI(title="Commerce Workbench", version=__version__, lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"]
    )

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin and origin != expected_origin:
                return JSONResponse({"detail": "不接受来自其他网站的修改请求"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return JSONResponse({"detail": "请使用 JSON 提交内容"}, status_code=415)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, exc: sqlite3.Error):
        return JSONResponse({"detail": "暂时无法保存或读取数据，请稍后重试"}, status_code=503)

    @app.get("/api/health")
    def health():
        try:
            database.workspace()
        except sqlite3.Error:
            return JSONResponse(
                {"status": "degraded", "database": "unavailable", "version": __version__},
                status_code=503,
            )
        return {"status": "ok", "database": "ready", "version": __version__}

    @app.get("/api/workspace")
    def get_workspace():
        return database.workspace()

    @app.put("/api/workspace")
    def update_workspace(payload: WorkspaceUpdate):
        try:
            return database.update_workspace(payload.name, payload.revision)
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="内容已在其他页面修改，请重新加载后保存")

    return app
