"""SQLite state store. Every step writes here, so a crashed run can resume."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    website TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    niche TEXT DEFAULT '',
    city TEXT DEFAULT '',
    source TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'found',
    audit_json TEXT DEFAULT '',
    score INTEGER DEFAULT 0,
    reasons TEXT DEFAULT '[]',
    draft_json TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    step TEXT NOT NULL,
    prospect_id INTEGER,
    ok INTEGER NOT NULL,
    ms INTEGER NOT NULL,
    detail TEXT DEFAULT ''
);
"""

UPDATABLE = {
    "status", "audit_json", "score", "reasons", "draft_json", "error", "name", "website",
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def dedupe_key(url: str) -> str:
    host = urlparse(normalize_url(url)).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class DB:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        if str(self.path) == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            conn = self._memory_conn
            yield conn
            conn.commit()
            return
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_prospect(self, name: str, website: str, niche="", city="", source="") -> int | None:
        website = normalize_url(website)
        key = dedupe_key(website)
        if not name.strip() or not key:
            return None
        now = time.time()
        with self._conn() as c:
            try:
                cur = c.execute(
                    "INSERT INTO prospects (name, website, dedupe_key, niche, city, source,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (name.strip(), website, key, niche, city, source, now, now),
                )
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get(self, pid: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM prospects WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def list(self, status: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM prospects", ()
        if status:
            sql += " WHERE status=?"
            args = (status,)
        sql += " ORDER BY score DESC, id ASC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def update(self, pid: int, **fields) -> None:
        bad = set(fields) - UPDATABLE
        if bad:
            raise ValueError(f"cannot update fields: {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
        with self._conn() as c:
            c.execute(
                f"UPDATE prospects SET {sets} WHERE id=?",
                (*fields.values(), time.time(), pid),
            )

    def log_event(self, step: str, pid: int | None, ok: bool, ms: int, detail: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO events (ts, step, prospect_id, ok, ms, detail) VALUES (?,?,?,?,?,?)",
                (time.time(), step, pid, int(ok), ms, detail[:500]),
            )

    def events(self, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) n FROM prospects GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    @staticmethod
    def reasons(p: dict) -> list[str]:
        try:
            return json.loads(p.get("reasons") or "[]")
        except json.JSONDecodeError:
            return []
