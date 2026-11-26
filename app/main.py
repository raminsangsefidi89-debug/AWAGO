"""FastAPI application factory: middleware, exception handlers, static, dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.api.errors import AppError
from app.config import get_settings
from app.db.engine import init_db
from app.logging_config import get_logger, set_correlation_id, setup_logging


class _RateLimiter:
    """Tiny in-memory per-IP token bucket (protects a local API from loops)."""

    def __init__(self, rate_per_minute: int = 300) -> None:
        self.capacity = rate_per_minute
        self.tokens: dict[str, float] = {}
        self.last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        import time

        now = time.monotonic()
        tokens = self.tokens.get(key, float(self.capacity))
        elapsed = now - self.last.get(key, now)
        tokens = min(float(self.capacity), tokens + elapsed * (self.capacity / 60.0))
        self.last[key] = now
        if tokens < 1.0:
            self.tokens[key] = tokens
            return False
        self.tokens[key] = tokens - 1.0
        return True


_rate_limiter = _RateLimiter()

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

DISCLAIMER = "For educational and analytical purposes only. This is not financial advice."


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    init_db()
    from app.services.scheduler import start_scheduler_if_enabled, stop_scheduler

    start_scheduler_if_enabled(settings)
    logger.info("AWAGO started (data_mode=%s, profile=%s)", settings.data_mode, settings.profile)
    yield
    stop_scheduler()
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

    # ---------------- Correlation-id middleware -------------------------
    @app.middleware("http")
    async def _correlation_middleware(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        cid = set_correlation_id(incoming[:64] if incoming else None)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled middleware-level error [%s]", cid)
            raise
        response.headers["X-Request-ID"] = cid
        # ETag for buffered GET responses (never for streams like SSE).
        content_type = response.headers.get("content-type", "")
        if (
            request.method == "GET"
            and "/api/v1/" in request.url.path
            and response.status_code == 200
            and not content_type.startswith("text/event-stream")
        ):
            import hashlib

            body = getattr(response, "body", None)
            if not body and hasattr(response, "body_iterator"):
                chunks = [chunk async for chunk in response.body_iterator]
                body = b"".join(chunks)
                rebuilt = Response(
                    content=body,
                    status_code=response.status_code,
                    headers={
                        k: v for k, v in response.headers.items() if k.lower() != "content-length"
                    },
                )
                rebuilt.headers["X-Request-ID"] = cid
                response = rebuilt
            if body:
                etag = '"' + hashlib.md5(body).hexdigest() + '"'
                response.headers["ETag"] = etag
                if request.headers.get("if-none-match") == etag:
                    return Response(status_code=304, headers={"ETag": etag, "X-Request-ID": cid})
        return response

    # ---------------- Per-IP rate limiting (API only) --------------------
    @app.middleware("http")
    async def _rate_limit_middleware(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            host = request.client.host if request.client else "unknown"
            if not _rate_limiter.allow(host):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests — slow down.",
                        }
                    },
                )
        return await call_next(request)

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
        code_map = {
            400: "bad_request",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
        }
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
            legacy_call: Any = templates.TemplateResponse
            return legacy_call("index.html", {"request": request, **context})

    return app


app = create_app()
