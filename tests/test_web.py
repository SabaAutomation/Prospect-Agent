import json

from fastapi.testclient import TestClient

from app.db import DB
from app.web import create_app


def seeded():
    db = DB(":memory:")
    pid = db.add_prospect("Acme <Dental>", "acme.test")
    db.update(
        pid, status="drafted", score=60, reasons=json.dumps(["no booking"]),
        draft_json=json.dumps({"subject": "Hi", "body": "Hello there", "method": "template"}),
    )
    return db, pid


def test_queue_escapes_html_and_lists_draft():
    db, pid = seeded()
    page = TestClient(create_app(db)).get("/").text
    assert "Acme &lt;Dental&gt;" in page and "<Dental>" not in page


def test_edit_then_approve_then_export():
    db, pid = seeded()
    client = TestClient(create_app(db))
    r = client.post(f"/prospect/{pid}/review", data={"subject": "New", "body": "Edited body", "action": "approve"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert db.get(pid)["status"] == "approved"
    assert "Edited body" in client.get("/export.csv").text


def test_reject_and_unknown_prospect():
    db, pid = seeded()
    client = TestClient(create_app(db))
    client.post(f"/prospect/{pid}/review", data={"subject": "s", "body": "b", "action": "reject"})
    assert db.get(pid)["status"] == "rejected"
    assert "not found" in client.get("/prospect/999").text.lower()
    assert client.get("/trace").status_code == 200
