"""Auditor agent: fetch a homepage politely and turn it into checkable findings.

All checks are deterministic. The LLM never decides what is wrong with a site,
so the facts in an outreach draft can always be traced back to the page.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import settings
from .db import normalize_url
from .models import Audit, Finding

ROBOTS_BLOCKED = "blocked by robots.txt"

BOOKING_PHRASES = (
    "book now", "book online", "book an appointment", "book appointment", "book a table",
    "book a consultation", "make an appointment", "make a reservation", "reserve a table",
    "schedule an appointment", "schedule a visit", "online booking", "request an appointment",
)
BOOKING_DOMAINS = (
    "calendly", "booksy", "setmore", "acuityscheduling", "zocdoc", "simplybook", "fresha",
    "opentable", "squareup", "square.site", "mindbody", "cal.com", "reservio",
)
PHONE_RE = re.compile(r"(\+?\d[\d\s\-().]{7,}\d)")
COPYRIGHT_RE = re.compile(r"(?:©|copyright|\(c\))\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.IGNORECASE)


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int = 0
    text: str = ""
    elapsed: float = 0.0
    error: str = ""


_robots_cache: dict[str, robotparser.RobotFileParser | None] = {}


def robots_allows(url: str) -> bool:
    """Respect robots.txt. If it cannot be read, fall back to allowed."""
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        parser: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
        try:
            r = httpx.get(
                f"{base}/robots.txt", timeout=6, follow_redirects=True,
                headers={"User-Agent": settings.user_agent},
            )
            if r.status_code == 200:
                parser.parse(r.text.splitlines())
            else:
                parser = None
        except httpx.HTTPError:
            parser = None
        _robots_cache[base] = parser
    parser = _robots_cache[base]
    return True if parser is None else parser.can_fetch(settings.user_agent, url)


def fetch(url: str, timeout: float = 12.0) -> FetchResult:
    url = normalize_url(url)
    if not robots_allows(url):
        return FetchResult(url=url, error=ROBOTS_BLOCKED)
    start = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers={"User-Agent": settings.user_agent}
        ) as client:
            r = client.get(url)
        return FetchResult(
            url=url, final_url=str(r.url), status=r.status_code,
            text=r.text[:500_000], elapsed=time.perf_counter() - start,
        )
    except httpx.HTTPError as e:
        return FetchResult(url=url, error=f"{type(e).__name__}: {e}")


def audit_page(res: FetchResult, today: date | None = None) -> Audit:
    today = today or date.today()
    audit = Audit(
        url=res.url, final_url=res.final_url, status_code=res.status,
        load_seconds=round(res.elapsed, 2),
    )
    if res.error or res.status >= 400 or not res.text.strip():
        why = res.error or f"HTTP {res.status}" if (res.error or res.status >= 400) else "empty page"
        audit.findings.append(Finding(
            code="unreachable", weight=40,
            detail=f"the website did not load properly ({why})",
            fix="rebuild or repair the site so customers can actually reach you",
            evidence=["load", "down", "reach", "working", "broken"],
        ))
        return audit

    soup = BeautifulSoup(res.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    low = text.lower()
    hrefs = [a.get("href", "").lower() for a in soup.find_all("a") if a.get("href")]
    audit.title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    add = audit.findings.append

    if (res.final_url or res.url).lower().startswith("http://"):
        add(Finding(
            code="no_https", weight=15,
            detail="the site is served over http, so browsers can show a 'Not secure' warning",
            fix="enable HTTPS so visitors don't see a security warning",
            evidence=["https", "secure", "security", "padlock"],
        ))
    if res.elapsed > 3.0:
        add(Finding(
            code="slow", weight=10,
            detail=f"the homepage took about {res.elapsed:.1f} seconds to load",
            fix="speed up the page so visitors don't leave while waiting",
            evidence=["slow", "seconds", "load", "speed"],
        ))
    if not soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        add(Finding(
            code="no_viewport", weight=20,
            detail="the page has no mobile viewport setting, so it likely looks broken on phones",
            fix="make the site mobile-friendly",
            evidence=["mobile", "phone", "phones", "responsive"],
        ))
    if not soup.find("meta", attrs={"name": re.compile("^description$", re.I)}):
        add(Finding(
            code="no_meta_description", weight=5,
            detail="the page has no search description, so Google picks random text to show",
            fix="add a proper search description",
            evidence=["google", "search", "description"],
        ))
    has_booking = any(p in low for p in BOOKING_PHRASES) or any(
        d in h for h in hrefs for d in BOOKING_DOMAINS
    )
    if not has_booking:
        add(Finding(
            code="no_booking", weight=20,
            detail="I couldn't find any online booking option on the homepage",
            fix="add simple online booking so customers can book without calling",
            evidence=["booking", "book", "appointment", "reservation"],
        ))
    if not any(("wa.me" in h or "whatsapp" in h) for h in hrefs) and "whatsapp" not in low:
        add(Finding(
            code="no_whatsapp", weight=15,
            detail="there is no WhatsApp contact button",
            fix="add a WhatsApp chat button with an automatic first reply",
            evidence=["whatsapp"],
        ))
    if not soup.find("form"):
        add(Finding(
            code="no_form", weight=10,
            detail="there is no contact form on the homepage",
            fix="add a short contact form that goes straight to your inbox",
            evidence=["contact form", "form", "enquiry", "inquiry"],
        ))
    if not any(h.startswith("tel:") for h in hrefs) and not PHONE_RE.search(text):
        add(Finding(
            code="no_phone", weight=5,
            detail="no phone number is visible on the homepage",
            fix="show a tap-to-call phone number",
            evidence=["phone", "call", "number"],
        ))
    years = [int(y) for y in COPYRIGHT_RE.findall(low) if 1990 <= int(y) <= today.year]
    if years and max(years) < today.year - 1:
        add(Finding(
            code="old_copyright", weight=10,
            detail=f"the footer still says copyright {max(years)}, which makes the site look abandoned",
            fix="refresh the site so it looks actively maintained",
            evidence=[str(max(years)), "copyright", "outdated", "abandoned", "footer"],
        ))
    return audit
