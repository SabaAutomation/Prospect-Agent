"""Writer agent: drafts a short, honest outreach message grounded in audit facts.

The model only phrases the message. Code validates it and retries, then falls
back to a plain template, so a weak local model can't ship a vague or spammy draft.
"""
from __future__ import annotations

import re

from .config import settings
from .llm import LLM, LLMError
from .models import Audit, Draft

SPAM_WORDS = (
    "guarantee", "guaranteed", "100%", "act now", "limited time", "risk-free",
    "click here", "once in a lifetime", "no obligation",
)
PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]|\{[^}]+\}|<[^>]+>")
MIN_WORDS, MAX_WORDS = 35, 140

SYSTEM = (
    "You write short, honest, polite first-contact emails for a freelancer. "
    "Use ONLY the facts provided. Never invent facts, prices, results, client names or claims "
    "about the recipient. Mention exactly one specific observation about their website, "
    "offer one simple improvement, and end with a low-pressure question. "
    f"Body length: {MIN_WORDS + 10} to {MAX_WORDS - 30} words. No hype, no emojis, no placeholders. "
    'Return JSON only: {"subject": "...", "body": "..."}. '
    "Do not include a signature; it is added automatically."
)


def footer(sender: str) -> str:
    return f"\n\n{sender}\nIf this isn't relevant, just reply 'no thanks' and I won't contact you again."


def validate(subject: str, body: str, audit: Audit) -> list[str]:
    problems: list[str] = []
    words = len(body.split())
    if not subject.strip() or len(subject) > 80:
        problems.append("subject must be non-empty and at most 80 characters")
    if words < MIN_WORDS:
        problems.append(f"body too short ({words} words)")
    if words > MAX_WORDS:
        problems.append(f"body too long ({words} words)")
    low = body.lower()
    if any(w in low for w in SPAM_WORDS):
        problems.append("contains spammy wording")
    if PLACEHOLDER_RE.search(subject + body):
        problems.append("contains a placeholder like [Name] or {name}")
    terms = [t.lower() for f in audit.top(2) for t in f.evidence]
    if terms and not any(t in low for t in terms):
        problems.append("does not mention a specific observation from the audit")
    return problems


def template_draft(name: str, audit: Audit, sender: str) -> Draft:
    top = audit.top(2)
    first = top[0] if top else None
    obs = first.detail if first else "your website could be doing more for you"
    fix = first.fix if first else "make it easier for customers to reach you"
    body = (
        f"Hi {name} team,\n\n"
        f"I was looking at your website and noticed that {obs}. "
        f"I help local businesses with this kind of thing, and a quick fix would be to {fix}. "
        f"Would it be useful if I sent over a short, free list of what I'd change?"
        f"{footer(sender)}"
    )
    return Draft(subject=f"A quick note about {name}'s website", body=body, method="template")


def write_draft(
    llm: LLM, name: str, niche: str, audit: Audit,
    sender: str | None = None, offer: str | None = None, attempts: int = 3,
) -> Draft:
    sender = sender or settings.sender_name
    offer = offer or settings.offer
    top = audit.top(2)
    facts = "\n".join(f"- {f.detail} (possible fix: {f.fix})" for f in top)
    feedback = ""
    for _ in range(attempts):
        user = (
            f"Recipient business: {name}\nType of business: {niche or 'local business'}\n"
            f"What I offer: {offer}\nVerified observations about their website:\n{facts}\n"
            f"{feedback}"
        )
        try:
            data = llm.chat_json(SYSTEM, user)
        except LLMError:
            break  # model offline or broken: use the template
        subject = str(data.get("subject", "")).strip()
        body = str(data.get("body", "")).strip()
        problems = validate(subject, body, audit)
        if not problems:
            return Draft(subject=subject, body=body + footer(sender), method="llm")
        feedback = "Your previous draft was rejected: " + "; ".join(problems) + ". Fix these."
    return template_draft(name, audit, sender)
