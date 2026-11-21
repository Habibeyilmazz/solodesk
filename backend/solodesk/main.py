"""The solodesk application: JSON API under /api, the built React app everywhere else."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .auth import LoginLimiter
from .config import Config, from_env
from .db import make_engine
from .deps import require_auth
from .routers import auth, clients, invoices, reports, settings, time

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
)


def create_app(config: Config | None = None) -> FastAPI:
    config = config or from_env()
    app = FastAPI(
        title="solodesk",
        version=__version__,
        description="Back office for freelancers. All money is in integer minor units "
        "(kuruş, cents, pence); rates are in basis points (2000 = 20%). "
        "Writes need the session cookie and an X-CSRF-Token header.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.config = config
    app.state.engine = make_engine(config.db_path)
    app.state.login_limiter = LoginLimiter()

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
        return response

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router)
    for module in (clients, time, invoices, reports, settings):
        app.include_router(module.router, dependencies=[Depends(require_auth)])

    @app.api_route(
        "/api/{path:path}", include_in_schema=False, methods=["GET", "POST", "PUT", "DELETE"]
    )
    def api_not_found(path: str):
        raise HTTPException(404, "Not found")

    if config.static_dir:
        index = config.static_dir / "index.html"
        app.mount("/assets", StaticFiles(directory=config.static_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (config.static_dir / path).resolve()
            if path and file.is_file() and file.is_relative_to(config.static_dir.resolve()):
                return FileResponse(file)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
