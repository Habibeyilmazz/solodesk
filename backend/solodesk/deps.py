"""Shared FastAPI dependencies: database session, authentication, CSRF."""

import hmac

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from .auth import hash_token
from .models import AuthSession, utcnow

SESSION_COOKIE = "solodesk_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db(request: Request):
    with Session(request.app.state.engine) as db:
        yield db


def current_session(request: Request, db: Session) -> AuthSession | None:
    token = request.cookies.get(SESSION_COOKIE)
    key = request.app.state.config.session_key
    sess = db.get(AuthSession, hash_token(token, key)) if token else None
    return sess if sess and sess.expires_at > utcnow() else None


def require_auth(request: Request, db: Session = Depends(get_db)) -> AuthSession:
    """Every /api route except login needs a session; every write also needs the CSRF token."""
    sess = current_session(request, db)
    if sess is None:
        raise HTTPException(401, "Not signed in")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent.encode(), sess.csrf_token.encode()):
            raise HTTPException(403, "Missing or invalid CSRF token")
    return sess


def get_or_404(db: Session, model, id_: int):
    row = db.get(model, id_)
    if row is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return row
