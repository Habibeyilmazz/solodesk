"""Runtime configuration, read once from the environment."""

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
    cookie_secure: bool = False
    static_dir: Path | None = None


def db_path_from_env() -> Path:
    data_dir = Path(os.environ.get("SOLODESK_DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "solodesk.db"


def from_env() -> Config:
    stored = os.environ.get("SOLODESK_PASSWORD_HASH", "")
    if not stored:
        password = os.environ.get("SOLODESK_PASSWORD", "")
        if len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(
                "Set SOLODESK_PASSWORD (at least 8 characters) or SOLODESK_PASSWORD_HASH "
                "before starting solodesk. See .env.example."
            )
        if password == "change-me-please":
            print("solodesk: still using the example password. Change SOLODESK_PASSWORD.", file=sys.stderr)
        stored = hash_password(password)
    static = Path(
        os.environ.get("SOLODESK_STATIC_DIR", Path(__file__).parents[2] / "frontend" / "dist")
    )
    return Config(
        db_path=db_path_from_env(),
        password_hash=stored,
        cookie_secure=os.environ.get("SOLODESK_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        static_dir=static if static.is_dir() else None,
    )
