"""Approval dashboard. A human reviews, edits and approves every draft.
There is deliberately no 'send' button: approved drafts are exported, not emailed."""
from __future__ import annotations

import csv
import html
import io
import json

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from .config import settings
from .db import DB
from .models import Audit
from .scorer import tier

CSS = """
body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1c1f24}
header{background:#1c1f24;color:#fff;padding:14px 24px;display:flex;gap:20px;align-items:center}
header a{color:#cfd6e4;text-decoration:none} header b{margin-right:auto}
main{max-width:1000px;margin:24px auto;padding:0 16px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #eceef2;vertical-align:top}
th{background:#eef0f4;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.pill{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600}
.hot{background:#fde2e2;color:#9b1c1c}.warm{background:#fff0cc;color:#8a5a00}.cold{background:#e4e8ee;color:#444}
.card{background:#fff;border-radius:8px;padding:18px;margin-bottom:16px}
input[type=text],textarea{width:100%;box-sizing:border-box;padding:8px;font:inherit;border:1px solid #cdd2da;border-radius:6px}
textarea{min-height:240px}
button{padding:8px 16px;border:0;border-radius:6px;font:inherit;cursor:pointer;margin-right:8px}
.ok{background:#1f8f4d;color:#fff}.no{background:#b3261e;color:#fff}.save{background:#dfe3ea}
.muted{color:#6b7380;font-size:13px} li{margin:4px 0}
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style>"
        "<header><b>Prospect Agent</b><a href='/'>Review queue</a><a href='/all'>All prospects</a>"
        "<a href='/trace'>Trace</a><a href='/export.csv'>Export approved</a></header>"
        f"<main>{body}</main>"
    )


def _table(rows: list[dict]) -> str:
    if not rows:
        return "<p class=muted>Nothing here yet. Run <code>python -m app.cli run --demo</code> first.</p>"
    out = ["<table><tr><th>Score</th><th>Business</th><th>Top issue</th><th>Status</th></tr>"]
    for p in rows:
        t = tier(p["score"])
        reasons = DB.reasons(p)
        out.append(
            f"<tr><td><span class='pill {t}'>{p['score']} {t}</span></td>"
            f"<td><a href='/prospect/{p['id']}'>{html.escape(p['name'])}</a><br>"
            f"<span class=muted>{html.escape(p['website'])}</span></td>"
            f"<td>{html.escape(reasons[0]) if reasons else ''}</td>"
            f"<td>{html.escape(p['status'])}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


def create_app(db: DB | None = None) -> FastAPI:
    db = db or DB(settings.db_path)
    app = FastAPI(title="Prospect Agent")

    @app.get("/", response_class=HTMLResponse)
    def queue():
        counts = db.counts()
        summary = " · ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "empty"
        return _page(
            "Review queue",
            f"<h2>Drafts waiting for your approval</h2><p class=muted>{html.escape(summary)}</p>"
            + _table(db.list("drafted")),
        )

    @app.get("/all", response_class=HTMLResponse)
    def everything():
        return _page("All prospects", "<h2>All prospects</h2>" + _table(db.list()))

    @app.get("/prospect/{pid}", response_class=HTMLResponse)
    def detail(pid: int):
        p = db.get(pid)
        if not p:
            return _page("Not found", "<p>Prospect not found.</p>")
        findings = ""
        if p["audit_json"]:
            audit = Audit.model_validate_json(p["audit_json"])
            findings = "<ul>" + "".join(
                f"<li><b>+{f.weight}</b> {html.escape(f.detail)}</li>" for f in audit.findings
            ) + "</ul>"
        draft = json.loads(p["draft_json"]) if p["draft_json"] else None
        form = "<p class=muted>No draft yet.</p>"
        if draft:
            form = (
                f"<form method=post action='/prospect/{pid}/review'>"
                f"<p class=muted>Written by: {html.escape(draft.get('method', ''))}. Edit freely before approving.</p>"
                f"<p><input type=text name=subject value='{html.escape(draft['subject'], quote=True)}'></p>"
                f"<p><textarea name=body>{html.escape(draft['body'])}</textarea></p>"
                "<button class=save name=action value=save>Save edits</button>"
                "<button class=ok name=action value=approve>Approve</button>"
                "<button class=no name=action value=reject>Reject</button></form>"
            )
        return _page(
            p["name"],
            f"<div class=card><h2>{html.escape(p['name'])}</h2>"
            f"<p><a href='{html.escape(p['website'], quote=True)}' target=_blank rel=noopener>{html.escape(p['website'])}</a>"
            f" · score {p['score']} · status <b>{html.escape(p['status'])}</b></p>"
            f"{'<p class=muted>Error: ' + html.escape(p['error']) + '</p>' if p['error'] else ''}"
            f"<h3>What the audit found</h3>{findings or '<p class=muted>Not audited yet.</p>'}</div>"
            f"<div class=card><h3>Draft</h3>{form}</div>",
        )

    @app.post("/prospect/{pid}/review")
    def review(pid: int, subject: str = Form(...), body: str = Form(...), action: str = Form("save")):
        p = db.get(pid)
        if p and p["draft_json"]:
            draft = json.loads(p["draft_json"])
            draft.update(subject=subject.strip(), body=body.strip())
            fields = {"draft_json": json.dumps(draft)}
            if action == "approve":
                fields["status"] = "approved"
            elif action == "reject":
                fields["status"] = "rejected"
            db.update(pid, **fields)
        return RedirectResponse("/" if action in ("approve", "reject") else f"/prospect/{pid}", status_code=303)

    @app.get("/trace", response_class=HTMLResponse)
    def trace():
        rows = "".join(
            f"<tr><td>{e['id']}</td><td>{e['step']}</td><td>{e['prospect_id'] or ''}</td>"
            f"<td>{'ok' if e['ok'] else 'FAIL'}</td><td>{e['ms']} ms</td><td>{html.escape(e['detail'])}</td></tr>"
            for e in db.events()
        )
        return _page(
            "Trace",
            "<h2>Recent agent steps</h2><table><tr><th>#</th><th>Step</th><th>Prospect</th>"
            f"<th>Result</th><th>Time</th><th>Detail</th></tr>{rows}</table>",
        )

    @app.get("/export.csv", response_class=PlainTextResponse)
    def export():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["name", "website", "score", "subject", "body"])
        for p in db.list("approved"):
            d = json.loads(p["draft_json"] or "{}")
            w.writerow([p["name"], p["website"], p["score"], d.get("subject", ""), d.get("body", "")])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    return app
