"""Scorer agent: a transparent, rule-based score. No LLM, so it is reproducible."""
from __future__ import annotations

from .models import Audit


def score(audit: Audit) -> tuple[int, list[str]]:
    total = min(100, sum(f.weight for f in audit.findings))
    reasons = [f.detail for f in audit.top(3)]
    return total, reasons


def tier(value: int) -> str:
    if value >= 50:
        return "hot"
    if value >= 25:
        return "warm"
    return "cold"
