"""Supervisor: runs Finder -> Auditor -> Scorer -> Writer, with retries, rate limits,
dedupe, trace events and resumable state. Nothing here ever sends a message."""
from __future__ import annotations

import json
import time
from typing import Callable

from . import finder as finder_mod
from .auditor import ROBOTS_BLOCKED, FetchResult, audit_page, fetch
from .config import settings
from .db import DB
from .llm import LLM
from .models import Audit
from .scorer import score as score_audit
from .writer import write_draft

Fetcher = Callable[[str], FetchResult]


class Pipeline:
    def __init__(
        self, db: DB, llm: LLM, fetcher: Fetcher = fetch,
        delay: float | None = None, min_score: int | None = None, log: Callable[[str], None] = print,
        osm_source: Callable[..., list[dict]] | None = None,
    ):
        self.db, self.llm, self.fetcher = db, llm, fetcher
        self.osm_source = osm_source
        self.delay = settings.request_delay if delay is None else delay
        self.min_score = settings.min_score if min_score is None else min_score
        self.log = log

    # ---- helpers -------------------------------------------------------
    def _run_step(self, step: str, pid: int | None, fn: Callable[[], str]) -> bool:
        start = time.perf_counter()
        try:
            detail = fn() or ""
            ok = True
        except Exception as e:  # one bad prospect must never stop the batch
            detail, ok = f"{type(e).__name__}: {e}", False
            if pid is not None:
                self.db.update(pid, status="failed", error=f"{step}: {detail}"[:300])
        self.db.log_event(step, pid, ok, int((time.perf_counter() - start) * 1000), detail)
        return ok

    # ---- agents --------------------------------------------------------
    def find(self, niche: str, city: str, limit: int, csv_path: str | None = None) -> int:
        rows: list[dict] = []

        def go() -> str:
            nonlocal rows
            source = self.osm_source or finder_mod.from_osm
            rows = finder_mod.from_csv(csv_path) if csv_path else source(niche, city, limit)
            return f"{len(rows)} candidates"

        if not self._run_step("find", None, go):
            return 0
        added = 0
        for row in rows[:limit]:
            pid = self.db.add_prospect(
                row["name"], row["website"], niche=row.get("niche") or niche,
                city=row.get("city") or city, source="csv" if csv_path else "osm",
            )
            added += 1 if pid else 0
        self.log(f"found {len(rows)} candidates, {added} new")
        return added

    def audit_pending(self) -> int:
        n = 0
        for p in self.db.list("found"):
            def go(p=p) -> str:
                res = self.fetcher(p["website"])
                if res.error == ROBOTS_BLOCKED:
                    self.db.update(p["id"], status="skipped_robots")
                    return "skipped: robots.txt disallows"
                audit = audit_page(res)
                self.db.update(p["id"], status="audited", audit_json=audit.model_dump_json())
                return f"{len(audit.findings)} findings"

            if self._run_step("audit", p["id"], go):
                n += 1
            time.sleep(self.delay)
        self.log(f"audited {n}")
        return n

    def score_pending(self) -> int:
        n = 0
        for p in self.db.list("audited"):
            def go(p=p) -> str:
                audit = Audit.model_validate_json(p["audit_json"])
                value, reasons = score_audit(audit)
                self.db.update(p["id"], status="scored", score=value, reasons=json.dumps(reasons))
                return f"score {value}"

            n += self._run_step("score", p["id"], go)
        self.log(f"scored {n}")
        return n

    def draft_pending(self) -> int:
        n = 0
        for p in self.db.list("scored"):
            if p["score"] < self.min_score:
                self.db.update(p["id"], status="skipped_low_score")
                continue

            def go(p=p) -> str:
                audit = Audit.model_validate_json(p["audit_json"])
                draft = write_draft(self.llm, p["name"], p["niche"], audit)
                self.db.update(p["id"], status="drafted", draft_json=draft.model_dump_json())
                return f"draft via {draft.method}"

            n += self._run_step("write", p["id"], go)
        self.log(f"drafted {n} (waiting for your approval)")
        return n

    # ---- whole run -----------------------------------------------------
    def run(self, niche: str, city: str, limit: int = 20, csv_path: str | None = None) -> dict:
        self.find(niche, city, limit, csv_path)
        self.audit_pending()
        self.score_pending()
        self.draft_pending()
        return self.db.counts()
