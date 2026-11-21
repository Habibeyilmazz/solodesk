"""The solodesk application: JSON API under /api, the built React app everywhere else."""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from . import __version__
from .auth import LoginLimiter
from .config import Config, from_env
from .db import make_engine
from .deps import current_session, require_auth
from .routers import auth, clients, imports, invoices, reports, settings, time

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)
# Swagger UI runs on the app's origin, so it could read the CSRF token and act as you.
# FastAPI's default loads "swagger-ui-dist@5", whatever 5.x is newest; pin one with hashes.
SWAGGER = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.1/"
SWAGGER_SRI = {
    "swagger-ui-bundle.js": "sha384-XFYN47VzPiDY6qPtxYKg0nqUeW/upo20xf1j2SUE7gT/i35FJB4cuS/71Iegzk8Z",  # noqa: E501
    "swagger-ui.css": "sha384-4c3vsE5f+trhFyHrFrLM1fFGUn531NIaC7dcqEWIJdoRQJ5CkJbSuSCwXLpaS1KF",
}
# The largest valid body is a Toggl import: 5,000,000 characters, as UTF-8 and JSON-escaped.
MAX_BODY_BYTES = 32 * 1024 * 1024
# Before sign-in the only body is a password (at most 1024 characters, JSON-escaped).
MAX_ANON_BODY_BYTES = 16 * 1024


class BodyLimit:
    """Refuse oversized request bodies before they are read into memory.

    FastAPI parses the whole body before it checks the session, and parsed JSON takes about
    25 times its size in memory, so anyone who can reach the port could exhaust it. Without
    a valid session cookie a body may be 16 KiB, with one 32 MiB.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_ANON_BODY_BYTES

        async def fits(size: int) -> bool:
            nonlocal limit
            # The session is looked up only for a body past the small limit, and off the
            # event loop: every transaction takes SQLite's write lock (see db.py).
            if size > limit == MAX_ANON_BODY_BYTES and await run_in_threadpool(signed_in, scope):
                limit = MAX_BODY_BYTES
            return size <= limit

        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and not await fits(int(length)):
            response = JSONResponse({"detail": "Request body too large"}, 413)
            return await response(scope, receive, send)
        received = 0

        async def counted_receive():  # a chunked body has no Content-Length to check up front
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if not await fits(received):
                raise HTTPException(413, "Request body too large")
            return message

        await self.app(scope, counted_receive, send)


def signed_in(scope) -> bool:
    with Session(scope["app"].state.engine) as db:
        return current_session(Request(scope), db) is not None


def create_app(config: Config | None = None) -> FastAPI:
    config = config or from_env()
    app = FastAPI(
        title="solodesk",
        version=__version__,
        description="Back office for freelancers. All money is in integer minor units "
        "(kuruş, cents, pence); rates are in basis points (2000 = 20%). "
        "Writes need the session cookie and an X-CSRF-Token header.",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.config = config
    app.state.engine = make_engine(config.db_path)
    app.state.login_limiter = LoginLimiter()
    app.add_middleware(BodyLimit)

    # Two inputs valid as JSON but impossible to store: a lone surrogate in text, an id beyond
    # SQLite's 64 bits. Both were a 500. Validation errors also stop echoing the input back,
    # since a surrogate in it cannot be encoded into the 422 response itself.
    @app.exception_handler(RequestValidationError)
    def invalid_request(_request, exc: RequestValidationError):
        detail = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": detail}, 422)

    @app.exception_handler(UnicodeEncodeError)
    @app.exception_handler(OverflowError)
    def unstorable(_request, _exc):
        return JSONResponse({"detail": "That value cannot be stored."}, 422)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        # Not on Swagger UI (it loads assets from a CDN) and not on PDFs: a CSP on the PDF
        # response itself can stop the browser's built-in viewer from rendering it.
        is_pdf = response.headers.get("content-type") == "application/pdf"
        if request.url.path != "/api/docs" and not is_pdf:
            response.headers["Content-Security-Policy"] = CSP
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/assets/"):
            # Vite puts a content hash in every file name under /assets
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/docs", include_in_schema=False)
    def docs() -> HTMLResponse:
        html = get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title="solodesk API",
            swagger_js_url=SWAGGER + "swagger-ui-bundle.js",
            swagger_css_url=SWAGGER + "swagger-ui.css",
            swagger_favicon_url="/favicon.svg",
        ).body.decode()
        for name, sri in SWAGGER_SRI.items():
            url = f'"{SWAGGER}{name}"'
            html = html.replace(url, f'{url} integrity="{sri}" crossorigin="anonymous"')
        return HTMLResponse(html)

    app.include_router(auth.router)
    for module in (clients, time, invoices, reports, settings, imports):
        app.include_router(module.router, dependencies=[Depends(require_auth)])

    @app.api_route(
        "/api/{path:path}", include_in_schema=False, methods=["GET", "POST", "PUT", "DELETE"]
    )
    def api_not_found(path: str):
        raise HTTPException(404, "Not found")

    if config.static_dir:
        index = config.static_dir / "index.html"
        # Compressed here, not app-wide: API responses carry the CSRF token and stay plain.
        assets = GZipMiddleware(StaticFiles(directory=config.static_dir / "assets"))
        app.mount("/assets", assets, name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (config.static_dir / path).resolve()
            if path and file.is_file() and file.is_relative_to(config.static_dir.resolve()):
                return FileResponse(file)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
