import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, delete

from ..auth import hash_token, verify_password
from ..deps import SESSION_COOKIE, current_session, get_db, require_auth
from ..models import AuthSession, LoginIn, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])
SESSION_LIFETIME = dt.timedelta(days=14)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter = request.app.state.login_limiter
    config = request.app.state.config
    who = request.client.host if request.client else "unknown"
    if wait := limiter.retry_after(who):
        raise HTTPException(
            429,
            f"Too many failed attempts. Try again in {wait // 60 + 1} minutes.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_password(body.password, config.password_hash):
        limiter.record_failure(who)
        raise HTTPException(401, "Wrong password")
    limiter.reset(who)

    db.exec(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hash_token(token), csrf_token=csrf, expires_at=utcnow() + SESSION_LIFETIME
        )
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=config.cookie_secure,
        path="/",
    )
    return {"authenticated": True, "csrf_token": csrf}


@router.get("/session")
def session_info(request: Request, db: Session = Depends(get_db)):
    """Who am I? The SPA calls this on load to pick up its CSRF token."""
    sess = current_session(request, db)
    if sess is None:
        return {"authenticated": False}
    return {"authenticated": True, "csrf_token": sess.csrf_token}


@router.post("/logout", status_code=204)
def logout(
    response: Response, sess: AuthSession = Depends(require_auth), db: Session = Depends(get_db)
):
    db.delete(sess)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
