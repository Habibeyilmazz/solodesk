"""Password hashing (scrypt, stdlib) and the login rate limiter."""

import hashlib
import hmac
import secrets
import threading
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


def hash_token(token: str, key: bytes) -> str:
    """Session tokens are stored hashed so a leaked database holds no usable cookies.

    The hash is keyed with a value derived from the password (Config.session_key), so
    changing the password ends every session that was opened with the old one.
    """
    return hmac.new(key, token.encode(), "sha256").hexdigest()


class LoginLimiter:
    """At most `max_failures` failed logins per client address within `window` seconds,
    and at most `max_total` from all addresses together.

    The total cap is what bounds guessing: a client address can be faked (X-Forwarded-For
    from a local process or a DNS-rebinding web page) or rotated (IPv6), the total cannot.
    The price is that a sustained attack also locks the owner out until it stops.

    shortcut: kept in process memory, so it resets on restart and is per-process;
    move it to the database if solodesk ever runs with more than one worker.
    """

    def __init__(
        self, max_failures: int = 5, window: int = 900, max_total: int = 50, clock=time.monotonic
    ):
        self.max_failures = max_failures
        self.max_total = max_total
        self.window = window
        self.clock = clock
        self._lock = threading.Lock()
        self._attempts: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()

    def claim(self, key: str) -> int:
        """Take one attempt for `key`. Returns 0, or the seconds to wait if none are left.

        The attempt is counted before the password is checked, so a burst of parallel
        guesses cannot all slip past the limit. A successful login gives it back via reset().
        """
        now = self.clock()
        with self._lock:
            if len(self._attempts) > 10_000:  # bound memory under a spray of source addresses
                self._attempts.clear()
            attempts = self._attempts.setdefault(key, deque())
            for queue, limit in ((attempts, self.max_failures), (self._all, self.max_total)):
                while queue and now - queue[0] >= self.window:
                    queue.popleft()
                if len(queue) >= limit:
                    return max(1, int(queue[0] + self.window - now))
            attempts.append(now)
            self._all.append(now)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
            if self._all:  # the successful attempt itself was no failure
                self._all.pop()


if __name__ == "__main__":
    import getpass

    print(hash_password(getpass.getpass("Password to hash: ")))
