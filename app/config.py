"""Settings come from environment variables, optionally loaded from a .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    model: str
    db_path: Path
    sender_name: str
    offer: str
    user_agent: str
    request_delay: float
    min_score: int


def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        model=os.getenv("PROSPECT_MODEL", "qwen2.5:7b"),
        db_path=Path(os.getenv("PROSPECT_DB", "data/prospects.db")),
        sender_name=os.getenv("PROSPECT_SENDER_NAME", "Your Name"),
        offer=os.getenv(
            "PROSPECT_OFFER",
            "websites with online booking and WhatsApp automation for local businesses",
        ),
        user_agent=os.getenv(
            "PROSPECT_USER_AGENT",
            "ProspectAgent/0.1 (+personal research; contact: set PROSPECT_USER_AGENT)",
        ),
        request_delay=float(os.getenv("PROSPECT_DELAY", "1.5")),
        min_score=int(os.getenv("PROSPECT_MIN_SCORE", "25")),
    )


settings = load_settings()
