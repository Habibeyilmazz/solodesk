from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from solodesk.auth import LoginLimiter, hash_password, verify_password
from solodesk.config import Config, from_env
from solodesk.main import create_app

from .conftest import PASSWORD, PASSWORD_HASH, make_app
from .test_concurrency import together


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
    assert [limiter.claim("a") for _ in range(4)] == [0, 0, 0, 60]
    assert limiter.claim("b") == 0  # other addresses are unaffected
    now[0] = 59
    assert limiter.claim("a") == 1
    now[0] = 60
    assert limiter.claim("a") == 0  # the window has passed
    limiter.reset("a")
    assert [limiter.claim("a") for _ in range(4)] == [0, 0, 0, 60]  # reset gives all three back


def test_limiter_caps_failures_from_all_addresses_together():
    now = [0.0]
    limiter = LoginLimiter(max_failures=3, window=60, max_total=5, clock=lambda: now[0])
    assert [limiter.claim(f"10.0.0.{i}") for i in range(6)] == [0, 0, 0, 0, 0, 60]
    now[0] = 60
    assert limiter.claim("10.0.0.99") == 0  # the window has passed
    assert limiter.claim("ok") == 0
    limiter.reset("ok")  # a successful login does not use up the shared budget
    assert [limiter.claim(f"x{i}") for i in range(5)] == [0, 0, 0, 0, 60]


def test_spoofed_forwarded_for_cannot_bypass_the_limit(app):
    """uvicorn trusts X-Forwarded-For from 127.0.0.1, so a local caller can name any address."""
    with TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*")) as client:
        codes = [
            client.post(
                "/api/auth/login",
                json={"password": "guess"},
                headers={"X-Forwarded-For": f"10.0.{i}.1"},
            ).status_code
            for i in range(52)
        ]
    assert codes == [401] * 50 + [429] * 2


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


def test_sessions_survive_a_restart_but_not_a_password_change(tmp_path, api):
    token = api.cookies["solodesk_session"]
    for session_key, expected in ((b"test-key", 200), (b"key-of-a-new-password", 401)):
        restarted = make_app(tmp_path / "test.db", session_key)
        with TestClient(restarted, cookies={"solodesk_session": token}) as client:
            assert client.get("/api/clients").status_code == expected


def test_session_key_follows_the_password(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLODESK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SOLODESK_PASSWORD_HASH", raising=False)

    def key(name, value):
        monkeypatch.setenv(name, value)
        return from_env().session_key

    first = key("SOLODESK_PASSWORD", "first-password")
    assert key("SOLODESK_PASSWORD", "first-password") == first  # same after a restart
    assert key("SOLODESK_PASSWORD", "second-password") != first
    stored = hash_password("first-password")
    assert key("SOLODESK_PASSWORD_HASH", stored) == stored.encode()  # a configured hash is the key


def test_login_is_rate_limited(anon):
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"password": "guess"}).status_code == 401
    blocked = anon.post("/api/auth/login", json={"password": PASSWORD})  # even the right one
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_parallel_guesses_cannot_outrun_the_limit(anon):
    codes = together(10, lambda _: anon.post("/api/auth/login", json={"password": "x"}).status_code)
    assert sorted(codes) == [401] * 5 + [429] * 5


def test_successful_logins_do_not_use_up_attempts(anon):
    for _ in range(8):
        assert anon.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_security_headers(anon):
    headers = anon.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_built_assets_are_cached_and_compressed(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1);" * 200)
    app = create_app(
        Config(
            db_path=tmp_path / "t.db",
            password_hash=PASSWORD_HASH,
            session_key=b"k",
            static_dir=tmp_path,
        )
    )
    with TestClient(app) as client:
        asset = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
        assert asset.headers["content-encoding"] == "gzip"
        assert "immutable" in asset.headers["cache-control"]
        assert client.get("/").headers["cache-control"] == "no-cache"
        api = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in api.headers
