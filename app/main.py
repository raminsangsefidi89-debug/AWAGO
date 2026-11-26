"""FastAPI application factory: middleware, exception handlers, static, dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.api.errors import AppError
from app.config import BASE_DIR, get_settings
from app.db.engine import init_db
from app.logging_config import get_logger, setup_logging

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

DISCLAIMER = "For educational and analytical purposes only. This is not financial advice."


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    init_db()
    logger.info("AWAGO started (data_mode=%s)", settings.data_mode)
    yield
    logger.info("AWAGO shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Foreign-exchange analysis and forecasting API with a Persian RTL dashboard. "
            "Forecasts are produced by machine-learning models evaluated with walk-forward "
            "validation and compared against simple baselines.\n\n"
            f"**Disclaimer:** {DISCLAIMER}"
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ---------------- Exception handlers (one consistent envelope) ----------
    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("AppError %s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed. Check the parameters.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {400: "bad_request", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code_map.get(exc.status_code, "http_error"),
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. See the server logs for details.",
                    "details": None,
                }
            },
        )

    # ---------------- Routers / static ------------------------------------
    app.include_router(api_router, prefix="/api/v1")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard(request: Request):
        """Persian RTL dashboard (single page)."""
        context = {
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "disclaimer": DISCLAIMER,
        }
        try:
            # Starlette >= 0.35 style: TemplateResponse(request, name, context)
            return templates.TemplateResponse(request, "index.html", context)
        except TypeError:
            # Older Starlette: TemplateResponse(name, {"request": request, ...})
            return templates.TemplateResponse("index.html", {"request": request, **context})

    return app


app = create_app()
