"""Password hashing (scrypt, stdlib) and the login rate limiter."""

import hashlib
import hmac
import secrets
import time
from collections import deque


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    except ValueError:
        return False
    return scheme == "scrypt" and hmac.compare_digest(_scrypt(password, salt), digest)


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_token(token: str) -> str:
    """Session tokens are stored hashed so a leaked database holds no usable cookies."""
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLimiter:
    """At most `max_failures` failed logins per client address within `window` seconds.

    shortcut: kept in process memory, so it resets on restart and is per-process;
    move it to the database if solodesk ever runs with more than one worker.
    """

    def __init__(self, max_failures: int = 5, window: int = 900, clock=time.monotonic):
        self.max_failures = max_failures
        self.window = window
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}

    def retry_after(self, key: str) -> int:
        """Seconds the caller must wait, or 0 if an attempt is allowed."""
        now = self.clock()
        attempts = self._failures.get(key)
        if not attempts:
            return 0
        while attempts and now - attempts[0] >= self.window:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
            return 0
        if len(attempts) < self.max_failures:
            return 0
        return max(1, int(attempts[0] + self.window - now))

    def record_failure(self, key: str) -> None:
        if len(self._failures) > 10_000:  # bound memory under a spray of source addresses
            self._failures.clear()
        self._failures.setdefault(key, deque()).append(self.clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


if __name__ == "__main__":
    import getpass

    print(hash_password(getpass.getpass("Password to hash: ")))
