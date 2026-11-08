"""One-command local bootstrap for Windows (also works on macOS/Linux).

- creates/conservatively repairs .env (generates a strong API key when missing)
- writes frontend/.env.local if missing
- runs Alembic migrations (SQLite by default)
- prints the API key to paste into the app's Settings page

Run through start_all.bat or start_all.ps1; running it directly is fine too.
"""

from __future__ import annotations

import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
FRONTEND_ENV = ROOT / "frontend" / ".env.local"
PLACEHOLDERS = {
    "",
    "your-strong-random-key-at-least-32-chars-long",
    "dev-insecure-key-change-me",
}


def generate_key() -> str:
    return secrets.token_urlsafe(48)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _set_key(text: str, key: str) -> str:
    if re.search(r"(?m)^API_KEY=", text):
        return re.sub(r"(?m)^API_KEY=.*$", f"API_KEY={key}", text)
    if not text.endswith("\n"):
        text += "\n"
    return text + f"API_KEY={key}\n"


def _current_key(text: str) -> str:
    match = re.search(r"(?m)^API_KEY=(.*)$", text)
    return match.group(1).strip() if match else ""


def ensure_env() -> str:
    if not ENV_PATH.exists():
        if not ENV_EXAMPLE.exists():
            raise SystemExit("Missing .env.example; cannot bootstrap .env")
        text = _read(ENV_EXAMPLE)
        key = generate_key()
        ENV_PATH.write_text(_set_key(text, key), encoding="utf-8")
        print("[bootstrap] created .env with a new API_KEY")
        return key

    text = _read(ENV_PATH)
    key = _current_key(text)
    if key in PLACEHOLDERS or len(key) < 32:
        key = generate_key()
        ENV_PATH.write_text(_set_key(text, key), encoding="utf-8")
        print("[bootstrap] replaced weak/empty API_KEY in .env")
    else:
        print("[bootstrap] .env already has a strong API_KEY")
    return key


def ensure_frontend_env() -> None:
    if FRONTEND_ENV.exists():
        return
    FRONTEND_ENV.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_ENV.write_text(
        "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n",
        encoding="utf-8",
    )
    print("[bootstrap] created frontend/.env.local")


def migrate() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    print("[bootstrap] initializing database (alembic upgrade head) ...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(
            "Database migration failed. Check DATABASE_URL in .env "
            "(local default is sqlite+aiosqlite:///./data/youtube_script_generator.db)."
        )
    print("[bootstrap] database ready")


def main() -> int:
    key = ensure_env()
    ensure_frontend_env()
    migrate()
    print()
    print("=" * 70)
    print("API KEY (paste it at http://localhost:3000/settings):")
    print(key)
    print("=" * 70)
    print("Tip: set GEMINI_API_KEY in .env (https://aistudio.google.com/apikey) and")
    print("optionally GROQ_API_KEY (https://console.groq.com) - both free, no card.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
