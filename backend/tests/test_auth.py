from fastapi.testclient import TestClient

from solodesk.auth import LoginLimiter, hash_password, verify_password

from .conftest import PASSWORD


def test_password_hash_roundtrip():
    stored = hash_password("s3cret-pass")
    assert stored.startswith("scrypt$") and "s3cret-pass" not in stored
    assert verify_password("s3cret-pass", stored)
    assert not verify_password("s3cret-pasS", stored)
    assert not verify_password("anything", "not-a-hash")
    assert hash_password("s3cret-pass") != stored  # salted


def test_limiter_blocks_after_max_failures_then_recovers():
    now = [0.0]
    limiter = LoginLimiter(max_failures=3, window=60, clock=lambda: now[0])
    for _ in range(3):
        assert limiter.retry_after("a") == 0
        limiter.record_failure("a")
    assert limiter.retry_after("a") == 60
    assert limiter.retry_after("b") == 0  # other addresses are unaffected
    now[0] = 59
    assert limiter.retry_after("a") == 1
    now[0] = 60
    assert limiter.retry_after("a") == 0


def test_api_requires_login(anon):
    for path in ("/api/clients", "/api/dashboard", "/api/invoices", "/api/export/invoices.csv"):
        assert anon.get(path).status_code == 401
    assert anon.get("/api/auth/session").json() == {"authenticated": False}
    assert anon.get("/api/health").status_code == 200


def test_login_sets_hardened_cookie(anon):
    assert anon.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    response = anon.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anon.get("/api/clients").status_code == 200
    assert anon.get("/api/auth/session").json()["csrf_token"] == response.json()["csrf_token"]


def test_writes_need_csrf_token(anon):
    csrf = anon.post("/api/auth/login", json={"password": PASSWORD}).json()["csrf_token"]
    body = {"name": "No Token Ltd"}
    assert anon.post("/api/clients", json=body).status_code == 403
    assert anon.post("/api/clients", json=body, headers={"X-CSRF-Token": "nope"}).status_code == 403
    assert anon.post("/api/clients", json=body, headers={"X-CSRF-Token": csrf}).status_code == 201


def test_logout_ends_the_session(api):
    assert api.post("/api/auth/logout").status_code == 204
    assert api.get("/api/clients").status_code == 401


def test_stolen_cookie_is_useless_after_logout(app, api):
    token = api.cookies["solodesk_session"]
    api.post("/api/auth/logout")
    with TestClient(app, cookies={"solodesk_session": token}) as thief:
        assert thief.get("/api/clients").status_code == 401


def test_login_is_rate_limited(anon):
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"password": "guess"}).status_code == 401
    blocked = anon.post("/api/auth/login", json={"password": PASSWORD})  # even the right one
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_security_headers(anon):
    headers = anon.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
