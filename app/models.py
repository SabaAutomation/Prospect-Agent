from __future__ import annotations

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """One concrete, checkable observation about a prospect's website."""

    code: str
    weight: int
    detail: str  # human-readable fact, e.g. "no online booking option found"
    fix: str = ""  # what the freelancer could offer
    evidence: list[str] = Field(default_factory=list)  # words a pitch should mention


class Audit(BaseModel):
    url: str
    final_url: str = ""
    status_code: int = 0
    load_seconds: float = 0.0
    title: str = ""
    findings: list[Finding] = Field(default_factory=list)

    def top(self, n: int = 2) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.weight, reverse=True)[:n]


class Draft(BaseModel):
    subject: str
    body: str
    method: str = "llm"  # "llm" or "template"
