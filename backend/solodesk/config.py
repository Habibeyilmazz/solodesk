"""Runtime configuration, read once from the environment."""

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .auth import hash_password

MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class Config:
    db_path: Path
    password_hash: str
    session_key: bytes  # changes with the password; see auth.hash_token
    cookie_secure: bool = False
    static_dir: Path | None = None


def db_path_from_env() -> Path:
    data_dir = Path(os.environ.get("SOLODESK_DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "solodesk.db"


def from_env() -> Config:
    stored = os.environ.get("SOLODESK_PASSWORD_HASH", "")
    session_key = stored.encode()
    if not stored:
        password = os.environ.get("SOLODESK_PASSWORD", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(
                "Set SOLODESK_PASSWORD (at least 8 characters) or SOLODESK_PASSWORD_HASH "
                "before starting solodesk. See .env.example."
            )
        if password == "change-me-please":
            print("solodesk: example password in use, change SOLODESK_PASSWORD", file=sys.stderr)
        stored = hash_password(password)
        session_key = hashlib.sha256(password.encode()).digest()  # the hash is salted anew
    static = Path(
        os.environ.get("SOLODESK_STATIC_DIR", Path(__file__).parents[2] / "frontend" / "dist")
    )
    return Config(
        db_path=db_path_from_env(),
        password_hash=stored,
        session_key=session_key,
        cookie_secure=os.environ.get("SOLODESK_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        static_dir=static if static.is_dir() else None,
    )
