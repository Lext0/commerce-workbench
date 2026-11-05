from contextlib import asynccontextmanager
from pathlib import Path
import base64
import binascii
import io
import sqlite3
import warnings

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from fastapi import FastAPI, HTTPException, Path as PathParameter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commerce_workbench import __version__
from commerce_workbench.config import Settings
from commerce_workbench.database import Database, DuplicateModel, ProductNotFound, RevisionConflict
from commerce_workbench.schemas import ProductFields, ProductList, ProductRead, ProductUpdate, WorkspaceUpdate


class ImageUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(max_length=4_000_000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    database = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        yield

    app = FastAPI(
        title="Commerce Workbench", version=__version__, lifespan=lifespan,
        docs_url=None, redoc_url=None,
    )
    static_dir = Path(__file__).with_name("static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
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
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "same-origin"
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

    @app.get("/")
    def home():
        return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/workspace")
    def get_workspace():
        return database.workspace()

    @app.put("/api/workspace")
    def update_workspace(payload: WorkspaceUpdate):
        try:
            return database.update_workspace(payload.name, payload.revision)
        except RevisionConflict:
            raise HTTPException(status_code=409, detail="内容已在其他页面修改，请重新加载后保存")

    @app.exception_handler(ProductNotFound)
    async def product_not_found(request: Request, exc: ProductNotFound):
        return JSONResponse({"detail": {"code": "not_found", "message": "没有找到这件商品"}}, status_code=404)

    @app.exception_handler(DuplicateModel)
    async def duplicate_model(request: Request, exc: DuplicateModel):
        return JSONResponse({"detail": {"code": "duplicate_model", "message": "这个型号已被使用，请检查后修改"}}, status_code=409)

    @app.get("/api/products", response_model=ProductList)
    def list_products(
        q: str = Query(default="", max_length=120),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1000000),
    ):
        return database.products(q, limit, offset)

    @app.post("/api/products", response_model=ProductRead, status_code=201)
    def create_product(payload: ProductFields):
        return database.create_product(payload.model_dump())

    @app.get("/api/products/{product_id}", response_model=ProductRead)
    def get_product(product_id: int = PathParameter(ge=1, le=9223372036854775807)):
        return database.product(product_id)

    @app.put("/api/products/{product_id}", response_model=ProductRead)
    def update_product(payload: ProductUpdate, product_id: int = PathParameter(ge=1, le=9223372036854775807)):
        try:
            return database.update_product(product_id, payload.model_dump(exclude={"revision"}), payload.revision)
        except RevisionConflict:
            raise HTTPException(status_code=409, detail={"code": "revision_conflict", "message": "商品已在其他页面修改，请载入最新内容后再保存"})

    @app.get("/api/products/{product_id}/image")
    def get_image(product_id: int):
        row = database.image(product_id)
        if row is None:
            raise HTTPException(status_code=404, detail="商品尚未设置图片")
        return Response(row["content"], media_type=row["content_type"], headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.put("/api/products/{product_id}/image")
    def put_image(payload: ImageUpload, product_id: int):
        try:
            content = base64.b64decode(payload.content, validate=True)
            if not content or len(content) > 3_000_000:
                raise ValueError("size")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 20_000_000:
                        raise ValueError("format or dimensions")
                    image.load()
                    content_type = Image.MIME[image.format]
        except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(status_code=422, detail="请选择不超过 3 MB 的有效 JPEG、PNG 或 WebP 图片")
        database.put_image(product_id, content_type, content)
        return {"saved": True}

    @app.delete("/api/products/{product_id}/image")
    def delete_image(product_id: int):
        database.delete_image(product_id)
        return {"deleted": True}

    @app.get("/api/products/{product_id}/listing")
    def get_listing(product_id: int):
        return database.listing(product_id)

    @app.post("/api/products/{product_id}/listing")
    def publish_listing(product_id: int):
        try:
            return database.publish(product_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.delete("/api/products/{product_id}/listing")
    def withdraw_listing(product_id: int):
        return database.withdraw(product_id)

    return app
