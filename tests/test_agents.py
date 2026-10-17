from datetime import date

from app.auditor import ROBOTS_BLOCKED, FetchResult, audit_page
from app.db import DB, dedupe_key
from app.demo import DEMO_ROWS, demo_fetch
from app.llm import LLMError
from app.pipeline import Pipeline
from app.scorer import score, tier
from app.writer import template_draft, validate, write_draft

TODAY = date(2026, 10, 17)


def audit_of(html: str, elapsed=0.5, final="https://x.test"):
    return audit_page(FetchResult(url=final, final_url=final, status=200, text=html, elapsed=elapsed), TODAY)


def codes(audit):
    return {f.code for f in audit.findings}


def test_bad_site_has_many_findings():
    a = audit_of("<html><body><p>Hello</p><footer>Copyright 2018</footer></body></html>", 4.0, "http://x.test")
    assert {"no_https", "slow", "no_viewport", "no_booking", "no_whatsapp", "no_form", "old_copyright"} <= codes(a)
    value, reasons = score(a)
    assert value >= 50 and tier(value) == "hot" and len(reasons) == 3


def test_good_site_scores_low():
    html = (
        '<html><head><meta name="viewport" content="x"><meta name="description" content="d"></head><body>'
        '<a href="https://calendly.com/a">Book online</a><a href="https://wa.me/1">chat</a>'
        '<a href="tel:+1555">call</a><form></form><footer>© 2026 Shop</footer></body></html>'
    )
    a = audit_of(html)
    assert codes(a) == set()
    assert tier(score(a)[0]) == "cold"


def test_unreachable_is_a_strong_finding():
    a = audit_page(FetchResult(url="https://x.test", error="ConnectError: boom"), TODAY)
    assert codes(a) == {"unreachable"} and score(a)[0] == 40


def test_validate_rejects_vague_spammy_and_placeholder_drafts():
    a = audit_of("<html><body>hi</body></html>")
    long_ok = "word " * 50
    assert any("specific" in p for p in validate("Hi", long_ok, a))
    assert any("spammy" in p for p in validate("Hi", long_ok + " guaranteed booking whatsapp", a))
    assert any("placeholder" in p for p in validate("Hi", long_ok + " [Name] booking", a))
    assert validate("Hi", ("booking " + long_ok), a) == []


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def chat_json(self, system, user):
        self.calls += 1
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_writer_retries_then_accepts_valid_draft():
    a = audit_of("<html><body>hi</body></html>")
    good = {"subject": "Online booking idea", "body": "I noticed there is no booking option on your site. " * 5}
    llm = FakeLLM([{"subject": "x", "body": "too short"}, good])
    d = write_draft(llm, "Acme", "gym", a, sender="Sam")
    assert d.method == "llm" and llm.calls == 2 and d.body.endswith("won't contact you again.")


def test_writer_falls_back_to_template_when_model_is_down_or_keeps_failing():
    a = audit_of("<html><body>hi</body></html>")
    assert write_draft(FakeLLM([LLMError("down")]), "Acme", "gym", a, sender="Sam").method == "template"
    bad = {"subject": "x", "body": "nope"}
    assert write_draft(FakeLLM([bad, bad, bad]), "Acme", "gym", a, sender="Sam").method == "template"
    assert "Acme" in template_draft("Acme", a, "Sam").body


def test_db_dedupes_by_host():
    db = DB(":memory:")
    assert db.add_prospect("A", "https://www.example.com/page") is not None
    assert db.add_prospect("A again", "example.com") is None
    assert dedupe_key("HTTP://WWW.Example.com") == "example.com"


def test_full_pipeline_with_demo_data_and_fake_llm(monkeypatch):
    db = DB(":memory:")
    llm = FakeLLM([LLMError("offline")] * 10)
    pipe = Pipeline(db, llm, fetcher=demo_fetch, delay=0, log=lambda m: None,
                    osm_source=lambda niche, city, limit=20: DEMO_ROWS)
    counts = pipe.run("dentist", "Demoville")
    assert counts.get("drafted", 0) >= 3
    assert counts.get("skipped_low_score", 0) >= 1  # the well-built demo site
    top = db.list("drafted")[0]
    assert top["draft_json"] and top["score"] >= 25
    steps = {e["step"] for e in db.events()}
    assert {"find", "audit", "score", "write"} <= steps


def test_robots_block_is_skipped_not_pitched(monkeypatch):
    db = DB(":memory:")
    db.add_prospect("Blocked Co", "blocked.test")
    blocked = lambda url: FetchResult(url=url, error=ROBOTS_BLOCKED)
    Pipeline(db, FakeLLM([]), fetcher=blocked, delay=0, log=lambda m: None).audit_pending()
    assert db.list()[0]["status"] == "skipped_robots"


def test_one_failure_does_not_stop_the_batch():
    db = DB(":memory:")
    db.add_prospect("Bad", "bad.test")
    db.add_prospect("Good", "good.test")

    def fetcher(url):
        if "bad" in url:
            raise RuntimeError("boom")
        return FetchResult(url=url, final_url=url, status=200, text="<html></html>", elapsed=0.1)

    Pipeline(db, FakeLLM([]), fetcher=fetcher, delay=0, log=lambda m: None).audit_pending()
    status = {p["name"]: p["status"] for p in db.list()}
    assert status == {"Bad": "failed", "Good": "audited"}
