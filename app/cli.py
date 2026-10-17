"""Command line entry point:  python -m app.cli <command>"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from .config import settings
from .db import DB
from .llm import OllamaClient
from .pipeline import Pipeline
from .scorer import tier


def cmd_doctor(args) -> int:
    ok, msg = OllamaClient().health()
    print(("OK   " if ok else "FAIL ") + msg)
    print(f"DB:   {settings.db_path}")
    if not ok:
        print("Note: without Ollama the agent still works, but drafts use the plain template.")
    return 0 if ok else 1


def cmd_run(args) -> int:
    db = DB(settings.db_path)
    llm = OllamaClient()
    if args.demo:
        from .demo import DEMO_ROWS, demo_fetch

        pipe = Pipeline(db, llm, fetcher=demo_fetch, delay=0,
                        osm_source=lambda niche, city, limit=20: DEMO_ROWS)
        counts = pipe.run("dentist", "Demoville", limit=20)
    else:
        if not args.csv and not (args.niche and args.city):
            print("Provide --niche and --city (OpenStreetMap) or --csv file.csv", file=sys.stderr)
            return 2
        pipe = Pipeline(db, llm)
        counts = pipe.run(args.niche or "", args.city or "", args.limit, args.csv)
    print("Status counts:", counts)
    print("Next: python -m app.cli serve   (then open http://127.0.0.1:8000)")
    return 0


def cmd_resume(args) -> int:
    pipe = Pipeline(DB(settings.db_path), OllamaClient())
    pipe.audit_pending()
    pipe.score_pending()
    pipe.draft_pending()
    return 0


def cmd_list(args) -> int:
    for p in DB(settings.db_path).list(args.status):
        print(f"#{p['id']:<3} {p['score']:>3} {tier(p['score']):<5} {p['status']:<18} {p['name']}")
    return 0


def cmd_export(args) -> int:
    rows = DB(settings.db_path).list("approved")
    writer = csv.writer(sys.stdout)
    writer.writerow(["name", "website", "score", "subject", "body"])
    for p in rows:
        d = json.loads(p["draft_json"] or "{}")
        writer.writerow([p["name"], p["website"], p["score"], d.get("subject", ""), d.get("body", "")])
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    from .web import create_app

    uvicorn.run(create_app(DB(settings.db_path)), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prospect-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check Ollama and the model").set_defaults(fn=cmd_doctor)
    r = sub.add_parser("run", help="find, audit, score and draft")
    r.add_argument("--niche", help="dentist, clinic, gym, real_estate, restaurant, salon, lawyer, accountant, school, or key=value")
    r.add_argument("--city")
    r.add_argument("--csv", help="use your own CSV (columns: name, website) instead of OpenStreetMap")
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--demo", action="store_true", help="offline demo data, no internet needed")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("resume", help="continue unfinished prospects").set_defaults(fn=cmd_resume)
    l = sub.add_parser("list", help="show prospects")
    l.add_argument("--status")
    l.set_defaults(fn=cmd_list)
    sub.add_parser("export", help="print approved drafts as CSV").set_defaults(fn=cmd_export)
    s = sub.add_parser("serve", help="open the approval dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
