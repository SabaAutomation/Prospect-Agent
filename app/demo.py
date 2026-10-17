"""Offline demo data so the whole flow works without internet or Ollama."""
from __future__ import annotations

from .auditor import FetchResult

DEMO_ROWS = [
    {"name": "Bright Smile Dental", "website": "brightsmile.demo", "city": "Demoville", "niche": "dentist"},
    {"name": "Northside Fitness", "website": "northsidefit.demo", "city": "Demoville", "niche": "gym"},
    {"name": "Green Leaf Clinic", "website": "greenleaf.demo", "city": "Demoville", "niche": "clinic"},
    {"name": "Modern Dental Care", "website": "moderndental.demo", "city": "Demoville", "niche": "dentist"},
    {"name": "Old Town Salon", "website": "oldtownsalon.demo", "city": "Demoville", "niche": "salon"},
]

_BAD = (
    "<html><head><title>Bright Smile Dental</title></head><body><h1>Welcome</h1>"
    "<p>We are a family dentist. Call us during office hours.</p>"
    "<footer>Copyright 2018 Bright Smile Dental</footer></body></html>"
)
_MID = (
    '<html><head><title>Northside Fitness</title><meta name="viewport" content="width=device-width">'
    '<meta name="description" content="Gym"></head><body><h1>Northside Fitness</h1>'
    '<a href="tel:+15550100">Call +1 555 0100</a><form><input name="email"></form>'
    "<footer>© 2025 Northside Fitness</footer></body></html>"
)
_GOOD = (
    '<html><head><title>Modern Dental Care</title><meta name="viewport" content="width=device-width">'
    '<meta name="description" content="Dentist"></head><body><h1>Modern Dental Care</h1>'
    '<a href="https://calendly.com/modern">Book online</a><a href="https://wa.me/15550123">WhatsApp</a>'
    '<a href="tel:+15550123">Call</a><form></form><footer>© 2026 Modern Dental Care</footer></body></html>'
)
_PAGES = {
    "brightsmile.demo": FetchResult(url="", final_url="http://brightsmile.demo", status=200, text=_BAD, elapsed=4.2),
    "northsidefit.demo": FetchResult(url="", final_url="https://northsidefit.demo", status=200, text=_MID, elapsed=1.1),
    "greenleaf.demo": FetchResult(url="", error="ConnectError: [demo] name not resolved"),
    "moderndental.demo": FetchResult(url="", final_url="https://moderndental.demo", status=200, text=_GOOD, elapsed=0.6),
    "oldtownsalon.demo": FetchResult(url="", final_url="https://oldtownsalon.demo", status=200, text=_BAD.replace("Bright Smile Dental", "Old Town Salon"), elapsed=2.0),
}


def demo_fetch(url: str) -> FetchResult:
    host = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    host = host[4:] if host.startswith("www.") else host
    base = _PAGES.get(host, FetchResult(url=url, error="ConnectError: [demo] unknown host"))
    return FetchResult(
        url=url, final_url=base.final_url, status=base.status, text=base.text,
        elapsed=base.elapsed, error=base.error,
    )
