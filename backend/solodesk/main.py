"""The solodesk application: JSON API under /api, the built React app everywhere else."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
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

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path != "/api/docs":  # Swagger UI loads its assets from a CDN
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
